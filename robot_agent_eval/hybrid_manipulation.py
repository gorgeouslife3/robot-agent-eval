"""Astra-scheduled VLA, learned grasp, and combined manipulation conditions.

Grasp networks propose poses, never unreviewed trajectories. All movement uses
the pinned rollout executor. No task-specific object names or recorded seeds.
"""
from pathlib import Path
import argparse
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.request
import uuid
import numpy as np
from PIL import Image
from .common import ROOT, read, write, sha

BACKENDS = ('vla', 'graspnet', 'vla_graspnet', 'anygrasp', 'vla_anygrasp')
COMMON_NOTE = '''This is a manipulation-backend comparison. The backend is
reported in each packet. pi05_infer is the legacy name of the proposal service:
provide target_text, an English description of the CURRENT object to grasp,
chosen from the original instruction and current RGB. Use an empty string for
pushing, placement, insertion, arm return, or while already holding the object.
Optionally supply grasp_pixel_rc=[row,col] on the object in the ORIGINAL head
image, or null for text-only SAM. The pixel must be grounded in current RGB;
inspect original images or scale a preview using its dimensions. A supplied
pixel selects point-mode SAM; it never bypasses segmentation or depth.
Grasp poses are fallible, current-frame hypotheses, not motion commands or
proof of contact. Review width, reach, object identity and approach clearance.
Decompose accepted goals into the existing bounded EEF commands, and inspect
execution before grasp/lift/place/return. Grasp-only has no VLA, student actions
or VLA failure gate; Astra plans all non-grasp phases and may use bounded EEF
actions directly. In VLA conditions, the original failure/intent gate applies.
Never invent a failed VLA proposal to justify a grasp-only action. Keep all
original task conditions, native termination and action bounds. Report whether
the learned candidate influenced your action in the public decision reason.'''


def validate_settings(settings):
    if settings['backend'] not in BACKENDS:
        raise ValueError('Unsupported manipulation backend')
    if 'anygrasp' in settings['backend']:
        raise ValueError('Real AnyGrasp SDK, checkpoint and licensed runtime required; mock forbidden')
    return settings


def candidate_packet(directory, target_text, sam, grasp_pixel_rc=None):
    from .ablation_perception import load_recorded_camera
    from .graspnet_probe import run as probe
    from .graspnet_calibration import contact_grasp_to_link
    camera = load_recorded_camera(directory)
    before = time.perf_counter()
    if grasp_pixel_rc is not None:
        pixel = np.asarray(grasp_pixel_rc)
        if pixel.shape != (2,) or not np.isfinite(pixel).all() or np.any(pixel < 0) or np.any(pixel >= camera['color'].shape[:2]):
            raise ValueError('Grasp pixel outside original head image')
        mask, receipt = sam.segment(camera['color'], point=grasp_pixel_rc)
    else:
        mask, receipt = sam.segment(camera['color'], text=target_text)
    mask_path = directory/'grasp_mask.png'
    Image.fromarray(mask.astype(np.uint8)*255).save(mask_path)
    out = directory/'graspnet'
    probe(directory, mask_path, out)
    candidates = []
    with np.load(out/'candidates.npz', allow_pickle=False) as data:
        for index in np.argsort(data['scores'])[::-1][:10]:
            matrix = data['world_poses'][index]
            variants = []
            for symmetry in (False, True):
                pose = matrix.copy()
                if symmetry:
                    pose[:3, :2] *= -1
                stages = {}
                for stage, clearance in (('pregrasp', .09), ('grasp', 0.)):
                    link, center = contact_grasp_to_link(pose, pregrasp_m=clearance)
                    stages[stage] = dict(position=link[:3], quaternion_wxyz=link[3:],
                                         contact_center_world_xyz=center)
                variants.append(stages)
            width = float(data['predicted_openings_m'][index])
            candidates.append(dict(index=int(index), score=float(data['scores'][index]),
                opening_m=width, nominal_width_compatible=0 <= width <= .065,
                link6_pose_variants=variants))
    return dict(target_text=target_text, grasp_pixel_rc=grasp_pixel_rc, sam=receipt, candidates=candidates,
        inference=read(out/'result.json'), elapsed_s=time.perf_counter()-before,
        identity_sha256=sha(out/'identity.json'),
        scope='Actual learned candidates converted to ARX link6; IK, collision and contact unverified',
        frame='environment_origin meters and wxyz; 9 cm pregrasp; Panda pad offset .1034 m, ARX TCP .145 m')


def serve(args):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from .ablation_perception import LocalSAM
    sam = LocalSAM(ROOT/'checkpoints/sam3/sam3.pt')
    write(args.output/'grasp_model_identity.json',dict(sam=read(ROOT/'results/sam3-download.json'),
        sam_load_s=sam.load_s,graspnet_source=read(ROOT/'results/contact-graspnet-source.json'),
        adapter_sha256=sha(Path(__file__))))
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            try:
                directory = Path(data['directory']).resolve()
                if not directory.is_relative_to(args.output.resolve()):
                    raise ValueError('Frame outside worker root')
                result = candidate_packet(directory, data['target_text'], sam, data.get('grasp_pixel_rc'))
                result['status'] = 'measured'
            except Exception as error:
                result = dict(status='measurement_error', error_type=type(error).__name__, error=str(error),
                              candidates=[], fallback_used=False)
            body = json.dumps(result, allow_nan=False).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers(); self.wfile.write(body)
    server = HTTPServer(('127.0.0.1', args.port), Handler)
    write(args.output/'grasp_ready.json', dict(port=args.port))
    server.serve_forever()


def install(module, config):
    settings = validate_settings(config['hybrid_manipulation'])
    backend = settings['backend']; uses_vla = backend.startswith('vla')
    original = module.RoboDojoTools
    original_specs = module.tool_specs
    original_turn = module.CodexPolicy._turn
    def turn(self, text):
        return original_turn(self, COMMON_NOTE+'\n\n'+text)
    module.CodexPolicy._turn = turn
    def specs(method='pi05_plus_gpt'):
        value = original_specs(method)
        for spec in value:
            if spec['name'] == 'pi05_infer':
                spec['description'] = 'Prepare a fresh proposal for the configured backend. '+COMMON_NOTE
                spec['inputSchema']['properties']['target_text'] = {'type': 'string'}
                spec['inputSchema']['required'].append('target_text')
                spec['inputSchema']['properties']['grasp_pixel_rc'] = {'anyOf':[
                    {'type':'null'}, {'type':'array','items':{'type':'integer'},'minItems':2,'maxItems':2}]}
                spec['inputSchema']['required'].append('grasp_pixel_rc')
            if spec['name'] == 'robodojo_execute' and not uses_vla:
                schema = spec['inputSchema']['properties']['response']['properties']
                schema['mode']['enum'] = ['eef']
                schema['steps']['maximum'] = 5
        return value
    module.tool_specs = specs
    if not uses_vla:
        skill = Path(os.environ['ROBOT_EVAL_CASE_FILE']).parent/'backend_skill'
        shutil.copytree(module.SKILL_ROOT, skill)
        shutil.copy2(module.SKILL_ROOT.parent/'robodojo-gpt-only-rollout/context/eef_control.md',
                     skill/'context/eef_control.md')
        (skill/'SKILL.md').write_text('''# Astra with learned grasp proposals
You are the autonomous Astra manipulation planner for dual ARX X5.
Use normal image, file and code tools as useful. Read the teacher context and
EEF contract for task and robot details. This condition disables VLA entirely.
Call robodojo_start once; then repeat pi05_infer (legacy name, no pi05 model)
and robodojo_execute using exact next_call paths and fresh output directories.
Provide target_text from current RGB and instruction, or empty for non-grasp
phases. Review learned poses and author bounded dual-arm EEF targets.
Only mode=eef and 1..5 steps are available; position within 5 cm and rotation
within .35 rad of measured current link6; explicit left/right poses, wxyz and
boolean gripper_closed required. Gripper opening 0=closed, 1=open.
Maintain structured task_progress and assessment from observed evidence.
There is no VLA action proposal or failure gate to override. Do not fabricate
failure. Use genuine aligned/uncertain/misaligned intent descriptions for your
proposed action. Never claim pose arrival, grasp or success from commands.
Continue until rollout_finished/native termination or an external budget stop.
No resets, rollback, object truth, reward queries, extra control connections or
unrecorded movements. Use English for public prose. Preserve original instruction.
'''+COMMON_NOTE)
        (skill/'gate_prompt.md').write_text('Assess observed progress and the planned action. No VLA takeover gate exists in this condition.\n')
        for path in (skill/'context').glob('*.md'):
            path.write_text('# Backend condition override\n'+COMMON_NOTE+'\n\n'+path.read_text())
        module.SKILL_ROOT = skill
        # module.main keeps the common service loop; no policy socket/model exists.
        from hybrid_rollout.robodojo.pi05_server import client as policy_client
        class NoVLA:
            def __init__(self, *args, **kwargs): pass
            def close(self): pass
        policy_client.Pi05Client = NoVLA
        from hybrid_rollout.robodojo.robodojo_server import client as rollout_client
        gate = rollout_client.validate_assessment
        def planner_assessment(response, request):
            if request.get('gate_policy') != 'astra_planner':
                return gate(response, request)
            # Validate progress/status fields without fabricating takeover evidence.
            gate(dict(response, mode='student'), request)
            return 'astra_planner'
        rollout_client.validate_assessment = planner_assessment

    class ManipulationHybrid(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.grasp_process = self.grasp_log = None

        def next_call(self):
            packet = super().next_call()
            if packet and not uses_vla and packet.get('tool') == 'robodojo_execute':
                packet['response'] = 'Supply a structured progress assessment and bounded eef decision; VLA disabled'
            return packet

        def start(self, **arguments):
            if uses_vla:
                return super().start(**arguments)
            from hybrid_rollout.robodojo import settings as pinned
            directory = self._check('robodojo_start', arguments)
            self.sim = self.rpc_factory('127.0.0.1', self.sim_port, timeout=600)
            self.meta = self.sim.request('metadata')
            if self.meta['task'] != self.task:
                raise RuntimeError('Launched task differs from requested task')
            reset = self.sim.request('reset', seed=self.seed, source='gpt_eef', policy_version=backend)
            self.meta['instruction'] = reset.get('instruction', self.meta['instruction'])
            self.episode, self.tick = reset['episode_id'], reset['step_id']
            self.require_native_termination = bool(reset.get('metadata', {}).get('evaluation_case'))
            self._rpc('begin_combination', teacher_model=pinned.MODEL, teacher_model_provider=pinned.PROVIDER,
                prompt_sha256=self.prompt_sha256, student_policy_version=None, student_policy_sha256=None)
            self._rpc('switch_control_source', source='gpt_eef', reason='Astra planner with learned grasp poses; VLA disabled')
            self.source = 'gpt_eef'
            self.run = dict(task=self.task, instruction=self.meta['instruction'], backend=backend,
                pi05_enabled=False, checkpoint=None, student_backend=None, action_space='bounded_eef',
                gate_policy='astra_planner', initial_state_hash=reset.get('initial_state_hash'),
                max_episode_steps=self.meta['max_episode_steps'], reset_metadata=reset.get('metadata'))
            write(self.output/'run.json', self.run); write(self.output/'history.json', [])
            self.phase = 'infer'
            return self._observation(directory)

        def _observation(self, directory, **kwargs):
            packet = super()._observation(directory, **kwargs)
            packet['manipulation_backend'] = backend
            packet['vla_enabled'] = uses_vla
            write(self.observation_path, packet)
            return packet

        def learned_proposal(self, text, pixel=None):
            if backend == 'vla' or not text.strip():
                return dict(status='not_requested', candidates=[], target_text=text)
            frame = self.output/'perception_host'/f'{self.tick:04d}'
            if self.grasp_process is None:
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', 0)); self.grasp_port = sock.getsockname()[1]
                self.grasp_log = (self.output/'perception_host/grasp_worker.log').open('w')
                self.grasp_process = subprocess.Popen([str(ROOT/'.venvs/frameworks/bin/python'),
                    '-m', 'robot_agent_eval.hybrid_manipulation', 'serve', '--output',
                    str(self.output/'perception_host'), '--port', str(self.grasp_port)],
                    cwd=ROOT, stdout=self.grasp_log, stderr=subprocess.STDOUT)
                deadline = time.monotonic()+180
                while not (self.output/'perception_host/grasp_ready.json').exists():
                    if self.grasp_process.poll() is not None:
                        raise RuntimeError('Grasp worker failed to load')
                    if time.monotonic() > deadline:
                        raise TimeoutError('Grasp worker load timeout')
                    time.sleep(.2)
            request = urllib.request.Request(f'http://127.0.0.1:{self.grasp_port}/measure',
                data=json.dumps(dict(directory=str(frame), target_text=text, grasp_pixel_rc=pixel)).encode(),
                headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=120) as response:
                value = json.load(response)
            value.update(step_id=self.tick, episode_id=self.episode)
            return value

        def infer(self, **arguments):
            text = arguments.pop('target_text', '')
            pixel = arguments.pop('grasp_pixel_rc', None)
            if uses_vla:
                packet = super().infer(**arguments)
            else:
                directory = self._check('pi05_infer', arguments)
                directory.mkdir(parents=True)
                self.proposal_path = directory/'proposal.json'
                # Pinned history counts discarded proposal rows even for EEF;
                # an empty audit array means there was no student proposal.
                self.actions = np.empty((0, 14), dtype=np.float32)
                self.prediction = dict(prediction_id=uuid.uuid4().hex)
                self.request = dict(self.observation_packet, request_id=uuid.uuid4().hex,
                    decision=len(self.history), gate_policy='astra_planner',
                    student_eef_trajectory=[], pi05_enabled=False,
                    **self.prediction)
                self.phase = 'execute'
                packet = dict(self.request, proposal_path=str(self.proposal_path), next_call=self.next_call())
            packet['grasp_proposal'] = self.learned_proposal(text, pixel)
            packet['manipulation_backend'] = backend
            self.request['grasp_proposal'] = packet['grasp_proposal']
            write(self.output/f'request_{len(self.history):03d}.json', self.request)
            write(Path(arguments['output_dir'])/'proposal.json', packet)
            return packet

        def execute(self, **arguments):
            if not uses_vla:
                response = arguments.get('response', {})
                if response.get('mode') != 'eef':
                    from hybrid_rollout.robodojo.io import InputError
                    raise InputError('Grasp-only supports bounded EEF actions; no VLA/student/edit mode')
                from hybrid_rollout.robodojo.robodojo_server import client as rollout_client
                rollout_client.validate_assessment(response, self.request)
                # Pinned decision recorder uses gpt_only to denote no student
                # takeover; backend identity remains explicit alongside it.
                response['evaluation_method'] = 'gpt_only'
                response['manipulation_backend'] = backend
            return super().execute(**arguments)

        def close(self):
            try: super().close()
            finally:
                if self.grasp_process is not None:
                    self.grasp_process.terminate()
                    try: self.grasp_process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        self.grasp_process.kill(); self.grasp_process.wait()
                if self.grasp_log: self.grasp_log.close()
    module.RoboDojoTools = ManipulationHybrid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['serve'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--port', type=int, required=True)
    serve(parser.parse_args())


if __name__ == '__main__': main()
