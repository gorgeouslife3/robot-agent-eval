"""CPU RGB color tracker and fallible public-state events; never emits actions.

This monitor is specific to the lavender shovel. A color match is only a
candidate identity and pixel co-motion is only a holding hypothesis. The
planner must inspect RGB. Unknown is not evidence of a failed grasp.
"""
from collections import deque
import cv2
import numpy as np


class Monitor:
    def __init__(self, config):
        self.config = config
        self.arm = None
        self.centroid = None
        self.missing = 0
        self.samples = deque(maxlen=12)
        self.closed = False
        self.close_anchor = None
        self.held_candidate = False
        self.trial_seen = False
        self.phase_cooldown = {}
        self.event_cooldown = {}
        self.recovery_pending = False

    def choose_arm(self, arm):
        if arm not in ('left', 'right'):
            raise ValueError('A measured arm is required')
        if self.arm != arm:
            self.arm = arm
            self.closed = False
            self.close_anchor = None
            self.held_candidate = False
            self.trial_seen = False
            self.samples.clear()

    def detected(self, rgb):
        hsv = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, np.array(self.config['hsv_low'], np.uint8),
                            np.array(self.config['hsv_high'], np.uint8))
        count, labels, statistics, centers = cv2.connectedComponentsWithStats(mask)
        candidates = [(s, c) for s, c in zip(statistics[1:], centers[1:])
                      if s[4] >= self.config['minimum_component_pixels']]
        if not candidates:
            return dict(status='unknown', reason='no_color_component', centroid_px=None,
                        components=0, identity_verified=False)
        if self.centroid is None:
            s, center = max(candidates, key=lambda item: item[0][4])
        else:
            near = [(s, c) for s, c in candidates if np.linalg.norm(c-self.centroid)
                    <= self.config['maximum_centroid_jump_pixels']]
            if not near:
                return dict(status='unknown', reason='tracking_jump', centroid_px=None,
                            components=len(candidates), identity_verified=False)
            s, center = min(near, key=lambda item: np.linalg.norm(item[1]-self.centroid))
        self.centroid = center.copy()
        return dict(status='color_candidate', reason='lavender_color_connected_component',
                    centroid_px=center.tolist(), bbox_xywh=s[:4].tolist(), pixels=int(s[4]),
                    components=len(candidates), identity_verified=False)

    @staticmethod
    def rate(events, step, cooldown, interval):
        result = []
        for event in events:
            if step-cooldown.get(event, -interval) >= interval:
                result.append(event)
                cooldown[event] = step
        return result

    def update(self, observation, step, pending_actions=None):
        detection = self.detected(observation['cam_high'])
        self.missing = self.missing+1 if detection['status']=='unknown' else 0
        phases, anomalies = [], []
        centroid = np.array(detection['centroid_px']) if detection['centroid_px'] is not None else None
        stage = 'locate' if self.arm is None else 'approach'
        progress = dict(hand_motion_m=None, target_motion_px=None, held_candidate=False,
                        physical_grasp_verified=False)
        if self.missing >= 2:
            anomalies.append('target_unobserved_two_acks')
        if self.arm is not None:
            i = 0 if self.arm=='left' else 1
            position = np.asarray(observation['eef_positions'][i], float)
            quaternion = np.asarray(observation['eef_quaternions_wxyz'][i], float)
            opening = float(observation['states'][i*7+6])
            closed = opening < .5
            if pending_actions is not None and not closed and len(pending_actions):
                if np.any(np.asarray(pending_actions)[:5, i*7+6] < .5):
                    phases.append('closure_in_next_ack')
            if closed and not self.closed:
                self.close_anchor = (position.copy(), centroid.copy() if centroid is not None else None)
                self.held_candidate = False
                self.trial_seen = False
                phases.append('closure_observed')
            if not closed and self.closed:
                self.close_anchor = None
                self.held_candidate = False
                self.trial_seen = False
            if closed and self.close_anchor is not None:
                before, pixel = self.close_anchor
                rise = float(position[2]-before[2])
                displacement = float(np.linalg.norm(centroid-pixel)) if centroid is not None and pixel is not None else None
                stage = 'close' if rise < self.config['trial_lift_m'] else 'test_lift'
                progress.update(hand_rise_since_close_m=rise, target_motion_since_close_px=displacement)
                if rise >= self.config['trial_lift_m'] and not self.trial_seen:
                    phases.append('first_test_lift_observed')
                    self.trial_seen = True
                if displacement is not None and rise >= self.config['trial_lift_m']:
                    if displacement >= self.config['co_motion_pixels']:
                        self.held_candidate = True
                    elif rise >= self.config['failed_lift_m']:
                        anomalies.append('test_lift_without_visible_motion')
                if self.held_candidate:
                    stage = 'lift_candidate'
                    if displacement is not None and displacement <= self.config['stationary_pixels']:
                        anomalies.append('previous_co_motion_lost')
                        self.held_candidate = False
            if self.recovery_pending:
                stage = 'recover'
                if not closed and (self.close_anchor is None):
                    phases.append('recovery_return_candidate')
                    self.recovery_pending = False
            self.closed = closed
            self.samples.append((step, position.copy(), quaternion.copy(), opening,
                                 centroid.copy() if centroid is not None else None))
            old = next((s for s in reversed(self.samples) if step-s[0]>=30), None)
            if old is not None:
                hand = float(np.linalg.norm(position-old[1]))
                angle = 2*np.arccos(np.clip(abs(np.dot(quaternion,old[2])),0.,1.))
                pixels = float(np.linalg.norm(centroid-old[4])) if centroid is not None and old[4] is not None else None
                progress.update(hand_motion_m=hand, hand_rotation_rad=float(angle), target_motion_px=pixels)
                if (hand < self.config['stationary_hand_m'] and angle < .03 and
                        abs(opening-old[3]) < .15 and pixels is not None and
                        pixels <= self.config['stationary_pixels']):
                    anomalies.append('no_progress_two_refresh_windows')
            progress['held_candidate'] = self.held_candidate
        phases = self.rate(phases, step, self.phase_cooldown, 15)
        anomalies = self.rate(anomalies, step, self.event_cooldown, 15)
        return dict(step_id=step, active_arm=self.arm, stage_candidate=stage,
                    detection=detection, progress=progress, phase_events=phases,
                    anomaly_events=anomalies, consecutive_unobserved_acks=self.missing,
                    warning='Color candidate and co-motion are fallible; inspect RGB, not ground truth')


def review_due(group, step, last_review, summary, initial=False):
    reasons = []
    if initial:
        reasons.append('initial')
    if step-last_review >= group['periodic_review_max_steps']:
        reasons.append('periodic')
    if group['phase_trigger']:
        reasons.extend('phase:'+x for x in summary['phase_events'])
    if group['anomaly_trigger']:
        reasons.extend('anomaly:'+x for x in summary['anomaly_events'])
    return reasons
