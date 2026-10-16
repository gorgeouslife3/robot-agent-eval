"""Compact Responses ReAct controller over the existing Direct EEF bridge.

Preview and offline tests use neither simulator connections nor credentials.
Robot-only action conversion and skill loading are deliberately API-independent.
"""
from __future__ import annotations

import argparse
import base64
from collections import deque
from copy import deepcopy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import time
import urllib.request

from .common import ROOT, read, write, sha, source_path

HARNESS = ROOT / 'harness'
STAGES = ('locate', 'approach', 'align', 'descend', 'close', 'test_lift', 'lift', 'recover')


class BudgetReached(RuntimeError):
    pass


def load_bundle(task, instruction=None, *, use_skill=True, root=None):
    """Resolve public task semantics only; never inspect a saved layout."""
    root = Path(root or os.environ.get('ROBOT_REACT_HARNESS_DIR', HARNESS))
    registry = read(root / 'skill-registry.json')
    candidates = [s for s in registry['skills'] if s['task'] == task]
    if instruction is not None:
        candidates = [s for s in candidates if all(w in instruction.lower()
                      for w in s['instruction_contains'])]
    if len(candidates) != 1:
        raise ValueError('No unique skill for this native task/instruction')
    entry = candidates[0]
    skill_path = (root / entry['path']).resolve()
    if not skill_path.is_relative_to(root.resolve()):
        raise ValueError('Skill path escapes harness directory')
    system = (root / 'system.md').read_text()
    skill = skill_path.read_text() if use_skill else ''
    prompt = system + ('\n\nTask skill:\n' + skill if skill else '')
    return dict(skill_id=entry['id'] if use_skill else None, use_task_skill=use_skill,
                prompt=prompt, prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                skill_sha256=sha(skill_path) if use_skill else None,
                registry_sha256=sha(root / 'skill-registry.json'))


def object_schema(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


def action_tool():
    vector = dict(type='array', items={'type': 'number'}, minItems=3, maxItems=3)
    properties = dict(
        stage={'type': 'string', 'enum': list(STAGES)},
        evidence={'type': 'string', 'maxLength': 400},
        expected_effect={'type': 'string', 'maxLength': 240},
        next_check={'type': 'string', 'maxLength': 240},
        memory=object_schema(dict(grasp_verified={'type': 'boolean'},
                                 facts={'type': 'array', 'items': {'type': 'string', 'maxLength': 180}, 'maxItems': 6})),
        arm={'type': 'string', 'enum': ['left', 'right']},
        translation_m=vector,
        rotation_xyz_deg=deepcopy(vector),
        gripper={'type': 'string', 'enum': ['keep', 'open', 'close']},
        control_steps={'type': 'integer', 'minimum': 1, 'maximum': 5})
    return dict(type='function', name='robot_action', strict=True,
                description='Move one arm by a bounded relative offset, hold the other, then observe. '
                'rotation_xyz_deg applies world-axis x, then y, then z rotations; [0,0,0] holds orientation. '
                'Translation norm <=0.05 m, net rotation <=0.35 rad. Native control, not a motion primitive.',
                parameters=object_schema(properties))


def multiply_quaternion(a, b):
    w, x, y, z = a
    v, i, j, k = b
    return [w*v-x*i-y*j-z*k, w*i+x*v+y*k-z*j,
            w*j-x*k+y*v+z*i, w*k+x*j-y*i+z*v]


def finite_vector(value, count):
    if (not isinstance(value, list) or len(value) != count or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in value)):
        raise ValueError('Expected a finite numeric vector')
    return value


def action_to_eef(args, packet):
    """Validate before mutation, then convert offsets to the Direct contract."""
    required = set(action_tool()['parameters']['required'])
    if not isinstance(args, dict) or set(args) != required:
        raise ValueError('Action fields do not match the tool contract')
    if args['stage'] not in STAGES or args['arm'] not in ('left', 'right'):
        raise ValueError('Unknown action stage or arm')
    for key, limit in [('evidence', 400), ('expected_effect', 240), ('next_check', 240)]:
        if not isinstance(args[key], str) or not args[key].strip() or len(args[key]) > limit:
            raise ValueError('Expected bounded nonempty public action text')
    memory = args['memory']
    if (not isinstance(memory, dict) or set(memory) != {'grasp_verified', 'facts'} or
            type(memory['grasp_verified']) is not bool or not isinstance(memory['facts'], list) or
            len(memory['facts']) > 6 or any(not isinstance(v, str) or len(v) > 180 for v in memory['facts'])):
        raise ValueError('Invalid bounded episode memory')
    n = args['control_steps']
    if type(n) is not int or not 1 <= n <= 5 or n > packet['remaining_steps']:
        raise ValueError('Control steps exceed action/native budget')
    if args['gripper'] not in ('keep', 'open', 'close'):
        raise ValueError('Unknown gripper command')
    delta = finite_vector(args['translation_m'], 3)
    if math.sqrt(sum(v*v for v in delta)) > .05 + 1e-9:
        raise ValueError('Translation exceeds 5 cm')
    xyz = finite_vector(args['rotation_xyz_deg'], 3)
    if any(abs(v) > 20.1 for v in xyz):
        raise ValueError('Rotation component exceeds local action range')
    dq = [1., 0., 0., 0.]
    for axis, angle in enumerate(xyz):
        half = math.radians(angle) / 2
        q = [math.cos(half), 0., 0., 0.]
        q[axis + 1] = math.sin(half)
        dq = multiply_quaternion(q, dq)
    angle = 2 * math.acos(min(1., abs(dq[0])))
    if angle > .35 + 1e-9:
        raise ValueError('Net rotation exceeds 0.35 rad')
    targets = {}
    for arm in ('left', 'right'):
        pose = packet['current_eef'][arm]
        p = list(finite_vector(pose['position'], 3))
        q = list(finite_vector(pose['quaternion_wxyz'], 4))
        norm = math.sqrt(sum(v*v for v in q))
        if abs(norm - 1) > 1e-4:
            raise ValueError('Measured quaternion is not normalized')
        closed = pose['gripper_opening_command'] < .5
        if arm == args['arm']:
            p = [a+b for a, b in zip(p, delta)]
            q = multiply_quaternion(dq, q)
            qnorm = math.sqrt(sum(v*v for v in q))
            q = [v/qnorm for v in q]
            if args['gripper'] != 'keep':
                closed = args['gripper'] == 'close'
        targets[arm] = dict(position=p, quaternion_wxyz=q, gripper_closed=closed)
    return dict(mode='eef', request_id=packet['request_id'], steps=n,
                reason=args['evidence'] + ' Expected: ' + args['expected_effect'], target=targets)


def image_content(path, edge):
    from PIL import Image
    with Image.open(path) as image:
        image = image.convert('RGB')
        image.thumbnail((edge, edge))
        stream = io.BytesIO()
        image.save(stream, format='JPEG', quality=90)
    return dict(type='input_image', image_url='data:image/jpeg;base64,' +
                base64.b64encode(stream.getvalue()).decode(), detail='high')


def build_payload(packet, bundle, config, *, memory=None, recent=(), previous=None, rejection=None):
    context = {k: packet[k] for k in ('instruction', 'step_id', 'remaining_steps', 'current_state', 'current_eef')}
    context.update(memory=memory or {'grasp_verified': False, 'facts': []},
                   recent_executed_actions=list(recent), action_rejection=rejection)
    content = [dict(type='input_text', text=json.dumps(context, ensure_ascii=False, allow_nan=False))]
    edge = config.get('images_max_edge', 480)
    if type(edge) is not int or edge < 64:
        raise ValueError('Invalid image preview size')
    for item in packet['images']:
        content.extend([dict(type='input_text', text='Current ' + item['camera']), image_content(item['path'], edge)])
    if previous:
        head = next(i for i in previous['images'] if i['camera'] == 'cam_high')
        content.extend([dict(type='input_text', text=f'Previous head view BEFORE last action, step {previous["step_id"]}'),
                        image_content(head['path'], edge)])
    return dict(model=config['model'], instructions=bundle['prompt'],
                reasoning={'effort': config['reasoning_effort']},
                input=[dict(role='user', content=content)], tools=[action_tool()],
                tool_choice={'type': 'function', 'name': 'robot_action'}, parallel_tool_calls=False,
                max_output_tokens=config.get('max_output_tokens_per_request', 8192), store=False, stream=False)


def parse_action(response, model):
    if response.get('model') != model or response.get('status') != 'completed':
        raise ValueError('Model identity mismatch or incomplete response')
    calls = [o for o in response.get('output', []) if o.get('type') == 'function_call']
    if len(calls) != 1 or calls[0].get('name') != 'robot_action':
        raise ValueError('Expected exactly one robot_action function call')
    return json.loads(calls[0]['arguments'])


class ResponsesClient:
    """Talk only to the owned loopback accounting proxy, with no actual key."""
    def __init__(self, config, output):
        self.config, self.output = config, Path(output)
        self.calls = self.total_tokens = 0
        self.url = os.environ['ROBOT_REACT_PROXY_URL'].rstrip('/') + '/responses'
        if not self.url.startswith('http://127.0.0.1:'):
            raise ValueError('The controller requires its owned local model proxy')

    def request(self, payload):
        if (self.calls >= self.config['max_model_calls_per_episode'] or
                self.total_tokens >= self.config['max_total_tokens_per_episode']):
            raise BudgetReached('Model call or total-token budget reached')
        call = self.calls
        self.calls += 1
        write(self.output / f'model_input_{call:03d}.json', payload)
        request = urllib.request.Request(self.url, data=json.dumps(payload, allow_nan=False).encode(),
                  headers={'Authorization': 'Bearer loopback-eval-token', 'Content-Type': 'application/json'})
        before = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.config['request_timeout_s'] + 5) as reply:
                response = json.load(reply)
        except Exception as error:
            # Do not expose provider response bodies or repeat an uncertain call.
            write(self.output / f'model_error_{call:03d}.json',
                  dict(error_type=type(error).__name__, elapsed_s=time.perf_counter()-before))
            raise RuntimeError('Model transport failed: ' + type(error).__name__) from None
        usage = response.get('usage')
        if not isinstance(usage, dict) or type(usage.get('total_tokens')) is not int:
            raise RuntimeError('Missing model token accounting')
        self.total_tokens += usage['total_tokens']
        # Persist public actions and accounting, never private reasoning content.
        write(self.output / f'model_output_{call:03d}.json',
              dict(status=response.get('status'), model=response.get('model'), usage=usage,
                   response_id=response.get('id'), elapsed_s=time.perf_counter()-before,
                   output=[o for o in response.get('output', []) if o.get('type') in ('function_call', 'message')]))
        if self.total_tokens >= self.config['max_total_tokens_per_episode']:
            raise BudgetReached('Configured total-token budget reached')
        return response


def run_loop(tools, model, config, output, bundle):
    """Observe automatically after each executed action; rejected actions do not advance memory."""
    output = Path(output)
    memory = {'grasp_verified': False, 'facts': []}
    recent = deque(maxlen=3)
    packet = tools.start(**{k: v for k, v in tools.next_call().items() if k != 'tool'})
    bundle = load_bundle(tools.task, packet['instruction'], use_skill=bundle['use_task_skill'])
    write(output / 'harness_identity.json', {k: v for k, v in bundle.items() if k != 'prompt'})
    (output / 'PROMPT.md').write_text(bundle['prompt'])
    previous = rejection = None
    rejected = 0
    while not packet['rollout_finished']:
        payload = build_payload(packet, bundle, config, memory=memory, recent=recent,
                                previous=previous, rejection=rejection)
        response = model.request(payload)
        args = parse_action(response, config['model'])
        try:
            action = action_to_eef(args, packet)
            # Upstream validation runs before any recorder or simulator mutation.
            from hybrid_rollout.robodojo.robodojo_server.gpt_only_client import validate_action
            validate_action(action, packet)
        except (ValueError, KeyError, TypeError) as error:
            rejected += 1
            rejection = str(error)
            with (output / 'react_trace.jsonl').open('a') as stream:
                stream.write(json.dumps(dict(event='rejected', step_id=packet['step_id'],
                                            action=args, error=rejection), allow_nan=False) + '\n')
            if rejected >= 3:
                raise RuntimeError('Three consecutive action validation failures')
            continue
        rejected = 0
        rejection = None
        before = time.perf_counter()
        next_call = tools.next_call()
        result = tools.act(observation_path=next_call['observation_path'], response=action,
                           output_dir=next_call['output_dir'])
        entry = dict(event='executed', sequence=len(tools.history), start_step=packet['step_id'],
                     end_step=result['step_id'], stage=args['stage'], evidence=args['evidence'],
                     expected_effect=args['expected_effect'], next_check=args['next_check'],
                     arm=args['arm'], translation_m=args['translation_m'], rotation_xyz_deg=args['rotation_xyz_deg'],
                     gripper=args['gripper'], control_steps_requested=args['control_steps'],
                     execution_observation_s=time.perf_counter()-before,
                     measured_eef_before=packet['current_eef'], measured_eef_after=result['current_eef'],
                     memory=args['memory'], native_terminal=result['rollout_finished'])
        with (output / 'react_trace.jsonl').open('a') as stream:
            stream.write(json.dumps(entry, allow_nan=False) + '\n')
        memory = deepcopy(args['memory'])
        recent.append({k: entry[k] for k in ('start_step', 'end_step', 'stage', 'evidence', 'expected_effect',
                                           'next_check', 'arm', 'translation_m', 'rotation_xyz_deg', 'gripper')})
        previous, packet = packet, result
        write(output / 'memory.json', memory)
    return packet.get('result')


def preview(observation, config_path, output, *, use_skill=True):
    """Build an inspectable request from recorded RGB; no key/API/simulator use."""
    packet, config = read(observation), read(config_path)
    bundle = load_bundle(packet['task'], packet['instruction'], use_skill=use_skill)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'PROMPT.md').write_text(bundle['prompt'])
    write(output / 'model_input.json', build_payload(packet, bundle, config))
    write(output / 'identity.json', {k: v for k, v in bundle.items() if k != 'prompt'})
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    dry = sub.add_parser('preview')
    dry.add_argument('--observation', type=Path, required=True)
    dry.add_argument('--config', type=Path, default=ROOT / 'configs/model.pilot.json')
    dry.add_argument('--output', type=Path, required=True)
    dry.add_argument('--generic', action='store_true')
    live = sub.add_parser('control')
    live.add_argument('--task', required=True)
    live.add_argument('--sim-port', type=int, required=True)
    live.add_argument('--layout', type=int, required=True)
    live.add_argument('--output', type=Path, required=True)
    live.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'preview':
        print(preview(args.observation, args.config, args.output, use_skill=not args.generic))
        return
    config = read(args.config)
    if config['wire_api'] != 'responses' or config.get('allow_model_fallback'):
        raise ValueError('Fixed Responses model configuration required')
    bundle = load_bundle(args.task, use_skill=config.get('use_task_skill', True))
    source_path()
    from hybrid_rollout.robodojo import settings
    settings.MODEL = config['model']
    settings.EFFORT = config['reasoning_effort']
    settings.PROVIDER = 'OpenAI'
    from hybrid_rollout.robodojo.robodojo_server.gpt_only_client import GPTOnlyTools
    args.output.mkdir(parents=True, exist_ok=False)
    tools = GPTOnlyTools(args.output, args.task, sim_port=args.sim_port, seed=args.layout,
                         max_decisions=config['max_decisions'], prompt_sha256=bundle['prompt_sha256'])
    try:
        result = run_loop(tools, ResponsesClient(config, args.output), config, args.output, bundle)
        print(json.dumps(result), flush=True)
    except Exception as error:
        write(args.output / 'failure.json', dict(error_type=type(error).__name__, error=str(error)))
        if tools.episode is not None and tools.phase != 'done':
            try:
                tools.finish('controller_budget' if isinstance(error, BudgetReached) else 'controller_error')
            except Exception as final_error:
                write(args.output / 'finish_error.json', dict(error_type=type(final_error).__name__))
        raise
    finally:
        tools.close()


if __name__ == '__main__':
    main()
