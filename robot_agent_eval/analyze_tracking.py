"""Compare model-requested EEF poses with observed robot link6 poses.

This measures robot geometry only. It cannot establish object localization,
grasp contact, or whether a pose was a good task choice.
"""
import argparse
import math
from pathlib import Path
from .common import read, write


def distance(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))


def rotation_degrees(a, b):
    norm = math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    if norm == 0:
        return None
    dot = min(1., abs(sum(x*y for x, y in zip(a, b))/norm))
    return math.degrees(2*math.acos(dot))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    run = p.parse_args().run
    observations = {}
    for path in sorted((run/'controller/observations').glob('*/observation.json')):
        obs = read(path)
        observations[obs['step_id']] = obs
    rows = []
    for decision in read(run/'controller/history.json'):
        response = decision['response']
        if response.get('mode') != 'eef':
            continue
        before = observations.get(decision['start_tick'])
        after = observations.get(decision['end_tick'])
        if before is None or after is None:
            continue
        arms = {}
        for arm in ('left', 'right'):
            target = response['target'][arm]
            start = before['current_eef'][arm]
            end = after['current_eef'][arm]
            arms[arm] = dict(
                start_position_error_m=distance(target['position'], start['position']),
                end_position_error_m=distance(target['position'], end['position']),
                observed_position_change_m=distance(start['position'], end['position']),
                start_rotation_error_deg=rotation_degrees(target['quaternion_wxyz'], start['quaternion_wxyz']),
                end_rotation_error_deg=rotation_degrees(target['quaternion_wxyz'], end['quaternion_wxyz']),
                gripper_closed_requested=target['gripper_closed'],
                gripper_opening_command_observed=end['gripper_opening_command'])
        rows.append(dict(decision=decision['decision'], start_tick=decision['start_tick'],
                         end_tick=decision['end_tick'], reason=response['reason'], arms=arms))
    write(run/'observed_tracking.json', dict(
        measurement='requested pose versus observed link6 pose in environment_origin; quaternion sign invariant',
        limitation='a short bounded action may intentionally approach without reaching its target; '
                   'gripper opening is a command, not verified contact; no object ground truth',
        rows=rows))
    print(run/'observed_tracking.json')


if __name__ == '__main__':
    main()
