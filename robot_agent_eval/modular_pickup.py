"""Parameterised perception ablations with a shared local tabletop executor.

Simulation-only pilot. Geometry-DLS is explicitly NOT GraspNet or VLA. Task
success remains the native evaluator's decision, outside the model context.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from pathlib import Path
import time
import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation
from scipy.ndimage import distance_transform_edt
from .common import ROOT, read, write, sha
from .framework_io import PublicEnv, append_trace
from .react_harness import ResponsesClient
from .perception_pilot import select_target, offline_geometry_audit
from .ablation_perception import (LocalSAM, locate, fit_target, backproject, project,
                                 top_down_link_pose, tcp_position, load_recorded_camera)


def pose_from_state(obs, arm):
    pose = np.asarray(obs['state'][arm+'_ee_pose'])
    return dict(position=pose[:3].tolist(), quaternion_wxyz=pose[3:7].tolist())


def pose_error(current, goal):
    q, t = current['quaternion_wxyz'], goal['quaternion_wxyz']
    angle = (Rotation.from_quat([*t[1:], t[0]]) * Rotation.from_quat([*q[1:], q[0]]).inv()).magnitude()
    return float(np.linalg.norm(np.asarray(current['position'])-goal['position'])), float(angle)


class Executor:
    def __init__(self, env):
        self.env = env

    def move(self, arm, goal, stage, max_steps, opening=1., minimum_steps=0):
        start = self.env.tick
        append_trace(self.env.output, dict(event='local_move_start', stage=stage, arm=arm, goal_link_pose=goal,
            goal_tcp_xyz=tcp_position(goal).tolist(), start_step=start, target_consumed=True))
        for _ in range(max_steps):
            if self.env.ended:
                break
            obs = self.env.get_obs()
            current = pose_from_state(obs, arm)
            position_error, angle_error = pose_error(current, goal)
            if position_error < .005 and angle_error < .06 and self.env.tick-start >= minimum_steps:
                break
            targets = {}
            for a in ('left', 'right'):
                p = pose_from_state(obs, a)
                p['gripper_closed'] = bool(float(np.asarray(obs['state'][a+'_ee_joint_state']).ravel()[0]) < .5)
                if a == arm:
                    delta = np.asarray(goal['position'])-p['position']
                    p['position'] = (np.asarray(p['position'])+delta*min(1., .05/max(np.linalg.norm(delta), 1e-12))).tolist()
                    q = p['quaternion_wxyz']; g = goal['quaternion_wxyz']
                    R = Rotation.from_quat([*q[1:], q[0]])
                    rot = (Rotation.from_quat([*g[1:], g[0]])*R.inv()).as_rotvec()
                    bounded = Rotation.from_rotvec(rot*min(1., .35/max(np.linalg.norm(rot), 1e-12)))*R
                    quat = bounded.as_quat(); p['quaternion_wxyz'] = [float(quat[3]), *quat[:3].tolist()]
                    p.update(gripper_closed=opening < .5, gripper_opening=opening)
                targets[a] = p
            proposal = self.env.call('eef_joint_target', targets=targets)
            row = proposal['action']
            self.env.step({f'{a}_{field}':row[offset:offset+n]
                for a, b in (('left', 0), ('right', 7))
                for field, offset, n in (('arm_joint_state', b, 6), ('ee_joint_state', b+6, 1))})
        actual = pose_from_state(self.env.observation, arm)
        err, angle = pose_error(actual, goal)
        append_trace(self.env.output, dict(event='local_move_end', stage=stage, start_step=start,
            end_step=self.env.tick, measured_link_pose=actual, measured_tcp_xyz=tcp_position(actual).tolist(),
            position_error_m=err, angle_error_rad=angle, reached=err < .01 and angle < .1))
        if not self.env.ended and (err >= .01 or angle >= .1):
            raise RuntimeError(f'Local motion did not converge at {stage}: {err:.4f}m / {angle:.4f}rad')
        return actual


def perceive(env, model, sam, config, previous=None):
    obs = env.get_obs(); cam = obs['vision']['cam_head']
    mode = config['ablation']['perception']
    before = time.perf_counter()
    if previous is None or mode != 'sam_depth':
        env.save_observation(f'perception-{env.tick:04d}')
        state = dict(instruction=obs['instruction'], state={k:np.asarray(v).tolist() for k,v in obs['state'].items()})
        image_path = env.output/'sensors'/f'perception-{env.tick:04d}'/'cam_head.png'
        recorded_seed = config['ablation'].get('recorded_seed_controller')
        if recorded_seed:
            if previous is not None or mode != 'sam_depth':
                raise ValueError('Recorded semantic seed is only a SAM-path initialization diagnostic')
            origin = Path(recorded_seed)
            old_camera = load_recorded_camera(origin/'sensors/initial')
            for field in ('depth','intrinsic_matrix','extrinsic_matrix'):
                if not np.array_equal(np.asarray(old_camera[field]), np.asarray(cam[field])):
                    raise ValueError('Recorded seed diagnostic requires identical initial depth/calibration')
            old_state = read(origin/'sensors/initial/state.json')
            if old_state['instruction'] != obs['instruction']:
                raise ValueError('Recorded semantic seed has different task')
            old = read(origin/'model_output_000.json')
            import json
            seed = json.loads(next(o['arguments'] for o in old['output'] if o.get('name') == 'select_target'))
            elapsed = 0.
            append_trace(env.output,dict(event='recorded_semantic_seed',origin=str(origin),
                origin_response_sha256=sha(origin/'model_output_000.json'),
                initial_depth_and_calibration_identical=True,rgb_bitwise_match=bool(np.array_equal(old_camera['color'],cam['color'])),
                condition='diagnostic replay; initial model generation cost remains at origin'))
        else:
            seed, elapsed = select_target(model, cam, state, image_path, config)
        pixel = seed['grasp_pixel']
    else:
        seed = previous['seed']; elapsed = 0.
        pixel = project(cam, [previous['target_xyz']])[0][0].round().astype(int).tolist()
    mask = None
    if mode == 'astra_rgb':
        xyz = seed['estimated_world_xyz']
        # Axis direction from calibrated RGB rays, with equal arbitrary depth;
        # actual depth values are NOT consumed by this perception condition.
        axis_points = backproject(cam, seed['axis_pixels'], [1., 1.])
        axis = axis_points[1]-axis_points[0]
    elif mode == 'astra_depth':
        geometry = locate(cam, pixel, estimator=config['ablation'].get('estimator', 'median'))
        xyz = geometry['world_xyz']
        endpoints = [locate(cam, p, estimator='median')['world_xyz'] for p in seed['axis_pixels']]
        axis = np.asarray(endpoints[1])-endpoints[0]
    elif mode == 'sam_depth':
        mask, receipt = sam.segment(cam['color'], point=pixel)
        geometry, _ = fit_target(cam, mask, pixel)
        location = locate(cam, pixel, mask=mask, estimator=config['ablation'].get('estimator', 'median'))
        xyz = location['world_xyz']; axis = np.array(geometry['axis_world'])
        append_trace(env.output, dict(event='local_sam', step=env.tick, pixel=pixel, receipt=receipt, geometry=geometry))
    else:
        raise ValueError('Unknown perception condition')
    axis[2] = 0
    if np.linalg.norm(axis) < 1e-6:
        raise ValueError('Degenerate grasp axis')
    axis /= np.linalg.norm(axis)
    if config['ablation'].get('symmetric_axis') == 'positive_y' and axis[1] < 0:
        axis *= -1
    result = dict(seed=seed, target_xyz=list(xyz), axis_world=axis.tolist(), step=env.tick,
                  perception=mode, astra_elapsed_s=elapsed, elapsed_s=time.perf_counter()-before)
    append_trace(env.output, dict(event='perception', **result))
    return result


def object_height(env, sam, prompt):
    """Public geometric verification, identical across perception conditions."""
    camera = env.get_obs()['vision']['cam_head']
    mask, receipt = sam.segment(camera['color'], text=prompt)
    depth = np.asarray(camera.get('distance_to_image_plane', camera['depth'])).squeeze()
    pixels = np.argwhere(mask & np.isfinite(depth) & (depth > 0))
    if len(pixels) < 20:
        raise ValueError('Verification has insufficient object depth')
    xyz = backproject(camera, pixels)
    result = dict(height_m=float(np.median(xyz[:, 2])), points=len(xyz), sam=receipt, step=env.tick)
    append_trace(env.output, dict(event='local_height_evidence', **result))
    return result['height_m']


class AnchorVerifier:
    """Use a point on the object's broad visible region to reduce grip occlusion.

The predicted anchor is a hypothesis only. Returned mask/depth must establish
actual object rise; a hand's commanded rise does not count as grasp evidence.
"""
    def __init__(self, env, sam, seed_pixel):
        self.env, self.sam = env, sam
        camera = env.get_obs()['vision']['cam_head']
        mask, receipt = sam.segment(camera['color'], point=seed_pixel)
        self.anchor_pixel = list(np.unravel_index(np.argmax(distance_transform_edt(mask)), mask.shape))
        self.anchor_world = np.array(locate(camera, self.anchor_pixel, mask=mask, estimator='median')['world_xyz'])
        self.initial_height = self.height(mask, camera)
        append_trace(env.output, dict(event='verifier_anchor', pixel=[int(x) for x in self.anchor_pixel],
            world_xyz=self.anchor_world.tolist(), initial_height_m=self.initial_height, sam=receipt))

    @staticmethod
    def height(mask, camera):
        depth = np.asarray(camera.get('distance_to_image_plane', camera['depth'])).squeeze()
        pixels = np.argwhere(mask & np.isfinite(depth) & (depth > 0))
        if len(pixels) < 20:
            raise ValueError('Verification has insufficient object depth')
        return float(np.median(backproject(camera, pixels)[:, 2]))

    def measure(self, hand_translation):
        camera = self.env.get_obs()['vision']['cam_head']
        predicted = self.anchor_world+np.asarray(hand_translation)
        pixel = project(camera, [predicted])[0][0].round().astype(int).tolist()
        mask, receipt = self.sam.segment(camera['color'], point=pixel)
        height = self.height(mask, camera)
        append_trace(self.env.output, dict(event='local_height_evidence', height_m=height,
            projected_anchor_pixel=pixel, predicted_anchor_is_only_hypothesis=True,
            sam=receipt, step=self.env.tick))
        return height


def learned_grasp(env, sam, perception):
    """Generate actual learned candidates, then apply explicit semantic filters."""
    from .graspnet_probe import run as probe
    from .graspnet_calibration import contact_grasp_to_link
    camera = env.get_obs()['vision']['cam_head']
    mask, receipt = sam.segment(camera['color'], point=perception['seed']['grasp_pixel'])
    env.save_observation('graspnet-input')
    mask_path = env.output/'graspnet-mask.png'
    Image.fromarray(mask.astype(np.uint8)*255).save(mask_path)
    out = env.output/'graspnet'
    probe(env.output/'sensors/graspnet-input', mask_path, out)
    choices=[]
    with np.load(out/'candidates.npz',allow_pickle=False) as data:
        for index,(matrix,score,width) in enumerate(zip(data['world_poses'],data['scores'],data['predicted_openings_m'])):
            link,center=contact_grasp_to_link(matrix)
            distance=float(np.linalg.norm(np.asarray(center)-perception['target_xyz']))
            accepted=distance <= .04 and matrix[2,2] < -.9 and float(width) <= .065
            append_trace(env.output,dict(event='graspnet_candidate_filter',index=index,score=float(score),
                opening_m=float(width),distance_to_semantic_target_m=distance,approach_z=float(matrix[2,2]),accepted=bool(accepted)))
            if accepted:choices.append((float(score),index,matrix.copy()))
    if not choices:raise ValueError('No learned grasp passes fixed target/approach/opening filters')
    score,index,matrix=max(choices,key=lambda x:x[0])
    arm=perception['seed']['arm'];current=pose_from_state(env.observation,arm)
    # Symmetric parallel-jaw orientations describe the same grasp. Choose the
    # nearer hand rotation without changing the contact centre/approach.
    mirrored=matrix.copy();mirrored[:3,:2]*=-1
    def angle(m):
        link,_=contact_grasp_to_link(m)
        return pose_error(current,dict(position=link[:3],quaternion_wxyz=link[3:]))[1]
    if angle(mirrored)<angle(matrix):matrix=mirrored
    append_trace(env.output,dict(event='graspnet_selected',index=index,score=score,matrix_world=matrix.tolist(),
        source='actual Contact-GraspNet candidates, not geometric replacement',sam=receipt))
    return matrix


def learned_link_goal(matrix,clearance_m):
    from .graspnet_calibration import contact_grasp_to_link
    link,_=contact_grasp_to_link(matrix,pregrasp_m=clearance_m)
    return dict(position=link[:3],quaternion_wxyz=link[3:])


def run(args, config):
    args.output.mkdir(parents=True, exist_ok=False)
    env = None
    try:
        env = PublicEnv(args.sim_port, args.layout, args.output, args.method)
        if args.method == 'graspnet_calibration':
            from .graspnet_calibration import run as calibrate
            calibrate(env, args, config)
            return
        if args.method == 'modular_calibration':
            camera = env.observation['vision']['cam_head']
            before = pose_from_state(env.observation, 'right')
            actual = Executor(env).move('right', before, 'hold_calibration', 1,
                opening=float(np.asarray(env.observation['state']['right_ee_joint_state']).ravel()[0]), minimum_steps=1)
            write(args.output/'calibration.json', dict(geometry=offline_geometry_audit(camera),
                held_pose_before=before, held_pose_after=actual, held_pose_error=pose_error(actual, before),
                native_steps=env.tick, scope='Public RGB-D, FK/DLS hold; no scored grasp, no native CuRobo IK'))
            return
        settings = config['ablation']
        if settings['action_backend'] not in ('geometry_dls','contact_graspnet_dls'):
            raise ValueError('Unvalidated action backend')
        if settings['action_backend']=='contact_graspnet_dls' and settings['perception']!='sam_depth':
            raise ValueError('First learned execution pilot requires validated SAM-depth input')
        sam = LocalSAM(ROOT/'checkpoints/sam3/sam3.pt')
        write(args.output/'sam_runtime.json', dict(load_s=sam.load_s))
        model = ResponsesClient(config, args.output)
        executor = Executor(env)
        perception = perceive(env, model, sam, config)
        arm = perception['seed']['arm']
        write(args.output/'text_provenance.json', dict(framework='modular_pickup', settings=settings,
            sam_identity=read(ROOT/'results/sam3-download.json'),
            semantic_seed='Recorded Astra RGB selection' if settings.get('recorded_seed_controller') else 'Fresh Astra RGB selection',
            action=settings['action_backend']+' + original robot-only bounded DLS', verification='same public SAM + depth height in all groups',
            source_sha256={n:sha(ROOT/'robot_agent_eval'/n) for n in ('modular_pickup.py','ablation_perception.py','perception_pilot.py','graspnet_probe.py','graspnet_calibration.py')}))
        # Prompt category comes from semantic selection, never layout contents.
        prompt = perception['seed']['target_prompt']
        verifier = (AnchorVerifier(env, sam, perception['seed']['grasp_pixel'])
                    if settings.get('verifier') == 'sam_anchor_depth' else None)
        initial_height = verifier.initial_height if verifier else object_height(env, sam, prompt)
        learned = learned_grasp(env,sam,perception) if settings['action_backend']=='contact_graspnet_dls' else None
        attempts = 2 if settings.get('recovery') else 1
        for attempt in range(attempts):
            write(args.output/f'attempt-{attempt:02d}-target.json', perception)
            xyz, axis = perception['target_xyz'], perception['axis_world']
            executor.move(arm, learned_link_goal(learned,.09) if learned is not None else top_down_link_pose(xyz, axis, .09), 'pregrasp', 75)
            if env.ended: return
            prior_xyz=np.array(xyz)
            perception = perceive(env, model, sam, config, perception)
            if perception['seed']['arm'] != arm:
                raise ValueError('Semantic selection changed arm during grasp')
            xyz, axis = perception['target_xyz'], perception['axis_world']
            if learned is not None:learned[:3,3]+=np.array(xyz)-prior_xyz
            executor.move(arm, learned_link_goal(learned,.09) if learned is not None else top_down_link_pose(xyz, axis, .09), 'realign', 20)
            if env.ended: return
            # Contact depth is robot geometry, not a remembered scene position.
            contact_clearance = (settings.get('first_contact_clearance_m', -.008)
                                 if attempt == 0 else -.018)
            goal = learned_link_goal(learned,0.) if learned is not None else top_down_link_pose(xyz, axis, contact_clearance)
            executor.move(arm, goal, 'descend', 35)
            if env.ended: return
            hold = pose_from_state(env.observation, arm)
            executor.move(arm, hold, 'close', 8, opening=0., minimum_steps=8)
            if env.ended: return
            test = deepcopy(hold); test['position'][2] += .03
            executor.move(arm, test, 'test_lift', 15, opening=0.)
            if env.ended: return
            current = pose_from_state(env.observation, arm)
            hand_delta = tcp_position(current)-tcp_position(hold)
            height = verifier.measure(hand_delta) if verifier else object_height(env, sam, prompt)
            verified = height-initial_height >= .012
            append_trace(args.output, dict(event='grasp_verification', attempt=attempt,
                initial_height_m=initial_height, after_height_m=height, verified=verified,
                note='Public median object height; independent native scoring remains authoritative'))
            if verified:
                lift = pose_from_state(env.observation, arm); lift['position'][2] += .10
                executor.move(arm, lift, 'lift', 30, opening=0.)
                write(args.output/'controller_outcome.json', dict(status='local_sequence_finished', native_terminal=env.ended))
                return
            if attempt+1 < attempts:
                current = pose_from_state(env.observation, arm)
                executor.move(arm, current, 'recover_open', 5, opening=1., minimum_steps=5)
                if env.ended: return
                perception = perceive(env, model, sam, config, perception)
        write(args.output/'controller_outcome.json', dict(status='grasp_not_verified', attempts=attempts, native_terminal=env.ended))
    except Exception as error:
        write(args.output/'failure.json', dict(error_type=type(error).__name__, error=str(error)))
        raise
    finally:
        if env: env.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--method', choices=['modular_pickup','modular_calibration','graspnet_calibration'], required=True)
    p.add_argument('--sim-port', type=int, required=True); p.add_argument('--layout', type=int, required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--config', type=Path, required=True)
    args = p.parse_args(); run(args, read(args.config))


if __name__ == '__main__': main()
