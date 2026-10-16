"""Critical invariants for substituting pose proposals for a VLA."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import os
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from robot_agent_eval.common import source_path
from robot_agent_eval.hybrid_manipulation import install, validate_settings

source_path()
from hybrid_rollout.robodojo.robodojo_server import client
from hybrid_rollout.robodojo.pi05_server import client as policy_client
from hybrid_rollout.robodojo.skill import run


class Manipulation(unittest.TestCase):
    def test_no_silent_backend_fallback(self):
        for backend in ('anygrasp', 'vla_anygrasp', 'unsupported'):
            with self.assertRaises(ValueError):
                validate_settings(dict(backend=backend))

    def test_grasp_only_has_no_vla_arrays_or_inference_and_preserves_bounds(self):
        class Policy:
            def _turn(self, text): return text
        module = SimpleNamespace(RoboDojoTools=client.RoboDojoTools, CodexPolicy=Policy,
                                 tool_specs=run.tool_specs, SKILL_ROOT=run.SKILL_ROOT)
        old_client = policy_client.Pi05Client
        old_gate = client.validate_assessment
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, ROBOT_EVAL_CASE_FILE=temp+'/case.json'):
            try:
                install(module, dict(hybrid_manipulation=dict(backend='graspnet')))
                controller = object.__new__(module.RoboDojoTools)
                controller.output = Path(temp)/'controller'; controller.output.mkdir()
                controller.phase = 'infer'; controller.tick = 0; controller.history = []
                controller.require_native_termination = True
                controller.observation_path = controller.output/'observation.json'
                pose = dict(position=[0.,0.,0.], quaternion_wxyz=[1.,0.,0.,0.])
                controller.observation_packet = dict(episode_id='test', step_id=0,
                    current_eef=dict(left=deepcopy(pose), right=deepcopy(pose)))
                target_dir = str(controller.output/'proposals/000')
                packet = controller.infer(observation_path=str(controller.observation_path),
                                           output_dir=target_dir, target_text='')
                self.assertFalse(packet['pi05_enabled'])
                self.assertEqual(packet['student_eef_trajectory'], [])
                self.assertEqual(packet['grasp_proposal']['status'], 'not_requested')
                self.assertEqual(controller.actions.shape,(0,14))
                self.assertFalse((Path(target_dir)/'actions.npz').exists())
                with self.assertRaisesRegex(Exception, 'no VLA/student/edit'):
                    controller.execute(proposal_path=packet['proposal_path'],
                        output_dir=str(controller.output/'observations/001'), response=dict(mode='student'))
                assessment = dict(task_progress=dict(verified_completed=[],currently_attempting='Approach',remaining=['Grasp']),
                    current_subgoal='Approach', execution_status='not_started', execution_evidence='Initial RGB',
                    expected_next_intent='Approach', predicted_next_intent='Approach', intent_status='aligned',
                    intent_evidence='Planned bounded approach')
                response = dict(request_id=packet['request_id'],mode='eef',steps=5,reason='Approach observed object',
                    target={a:dict(pose,gripper_closed=False) for a in ('left','right')},assessment=assessment)
                self.assertEqual(client.validate_assessment(response,controller.request), 'astra_planner')
                controller.validate(response, controller.request)
                response['target']['right']['position'] = [.051,0.,0.]
                with self.assertRaisesRegex(ValueError,'5 cm'):
                    controller.validate(response,controller.request)
                response['target']['right']['position'] = [0.,0.,0.]
                controller.source='gpt_eef'; controller.episode='test'; controller.max_decisions=60
                controller.counters=dict(student_steps=0,edited_steps=0,recovery_steps=0,predictions=0)
                rpc_calls=[]
                def rpc(op,**kwargs):
                    rpc_calls.append(op)
                    if op=='record_codex_decision': return dict(physical_steps=0)
                    if op=='eef_joint_target': return dict(action=np.zeros(14),diagnostics={})
                    if op=='chunk_step':
                        tick=controller.tick+1
                        return dict(step_id=tick,steps=[dict(valid=True,terminated=False,truncated=False,
                            success=False,executed_action=np.zeros(14),obs=dict(states=np.zeros(14)))])
                    raise AssertionError(op)
                controller._rpc=rpc
                controller._observation=lambda directory,**kwargs:dict(step_id=controller.tick)
                result=controller.execute(proposal_path=packet['proposal_path'],
                    output_dir=str(controller.output/'observations/001'),response=response)
                self.assertEqual(result['step_id'],5)
                self.assertEqual(rpc_calls.count('chunk_step'),5)
                self.assertEqual(controller.history[0]['discarded_student_steps'],0)
                self.assertEqual(controller.history[0]['selected_student_steps'],0)
                self.assertEqual(controller.history[0]['takeover_trigger'],'astra_planner')
            finally:
                policy_client.Pi05Client = old_client
                client.validate_assessment = old_gate

    def test_combined_preserves_original_vla_input(self):
        class Original:
            def infer(self, **arguments):
                self.consumed = deepcopy(self.obs)
                self.request = dict(step_id=4)
                return dict(student_eef_trajectory=[1,2,3])
        class Policy:
            def _turn(self,text): return text
        module = SimpleNamespace(RoboDojoTools=Original,CodexPolicy=Policy,tool_specs=run.tool_specs)
        install(module,dict(hybrid_manipulation=dict(backend='vla_graspnet')))
        with tempfile.TemporaryDirectory() as temp:
            controller=object.__new__(module.RoboDojoTools)
            controller.output=Path(temp); controller.history=[]
            controller.obs=dict(states=np.arange(14),instruction='Original full task',cam_high=np.zeros((2,2,3)))
            original=deepcopy(controller.obs)
            controller.learned_proposal=lambda text,pixel=None:dict(target_text=text,candidates=[dict(index=3)])
            packet=controller.infer(output_dir=temp,target_text='red block')
            self.assertEqual(packet['student_eef_trajectory'],[1,2,3])
            self.assertEqual(packet['grasp_proposal']['target_text'],'red block')
            self.assertEqual(controller.consumed['instruction'],original['instruction'])
            self.assertTrue(np.array_equal(controller.consumed['states'],original['states']))
            self.assertNotIn('grasp_proposal',controller.consumed)


if __name__ == '__main__': unittest.main()
