"""Paired experiment invariants; no model calls, GPU or robot required."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import numpy as np
from robot_agent_eval.hybrid_perception import depth_evidence,segment_evidence,validate_settings,install
from robot_agent_eval.permissions import isolate
from robot_agent_eval.common import ROOT
from robot_agent_eval.compare_hybrid_perception import has_measurement


class HybridPerception(unittest.TestCase):
    def camera(self):
        return dict(color=np.zeros((24,32,3),np.uint8),depth=np.ones((24,32)),
            intrinsic_matrix=np.array([[100,0,16],[0,100,12],[0,0,1.]]),extrinsic_matrix=np.eye(4))

    def test_invalid_depth_is_unknown_not_fabricated_measurement(self):
        camera=self.camera();camera['depth'][6,8]=np.nan
        result=depth_evidence(camera,rows=2,cols=2)
        self.assertEqual(result['samples'][0]['pixel_rc'],[6,8])
        self.assertIsNone(result['samples'][0]['depth_m'])
        self.assertTrue(all(s['depth_m']==1. for s in result['samples'][1:]))

    def test_surface_geometry_uses_actual_mask_and_camera_not_fixed_grasp(self):
        camera=self.camera();mask=np.zeros((24,32),bool);mask[6:18,20:28]=True
        evidence=segment_evidence(camera,mask,dict(score=.7),'object from task')
        self.assertEqual(evidence['bbox_rc'],[[6,20],[17,27]])
        self.assertTrue(np.allclose(evidence['visible_surface_median_world_xyz'],[.075,.005,-1]))
        shifted=deepcopy(camera);shifted['extrinsic_matrix'][0,3]=.3
        second=segment_evidence(shifted,mask,dict(score=.7),'object from task')
        self.assertAlmostEqual(second['visible_surface_median_world_xyz'][0],.375)
        self.assertNotIn('grasp_target',evidence);self.assertNotIn('action',evidence)

    def test_supplement_enters_proposal_without_modifying_pi05_observation_or_tools(self):
        class Original:
            def infer(self,**arguments):
                self.student_input=deepcopy(self.obs)
                return dict(step_id=3,student_eef_trajectory=[1,2,3])
        class Policy:
            def _turn(self,text):return text
        saved=[]
        module=SimpleNamespace(RoboDojoTools=Original,CodexPolicy=Policy,
            write_json=lambda path,data:saved.append((path,data)))
        install(module,dict(hybrid_perception=dict(mode='raw_depth')))
        controller=object.__new__(module.RoboDojoTools)
        controller.obs=dict(states=np.arange(14),cam_high=np.zeros((2,2,3),np.uint8),instruction='pick')
        original_obs=deepcopy(controller.obs)
        controller.evidence=dict(frame=dict(step_id=3),depth_grid=dict(samples=[]))
        result=controller.infer(output_dir='/tmp/unused-hybrid-proposal')
        self.assertEqual(result['perception_evidence'],controller.evidence)
        self.assertEqual(result['student_eef_trajectory'],[1,2,3])
        self.assertEqual(controller.student_input['instruction'],original_obs['instruction'])
        self.assertTrue(np.array_equal(controller.student_input['states'],original_obs['states']))
        self.assertTrue(np.array_equal(controller.student_input['cam_high'],original_obs['cam_high']))
        self.assertNotIn('perception_evidence',controller.student_input)

    def test_raw_host_evidence_denied_to_agent(self):
        audit=ROOT/'runs/test-hybrid-permission/controller/codex_workspace'
        rules={'permissions.rollout_agent.filesystem':{}}
        result=isolate(rules,audit)
        self.assertEqual(result['permissions.rollout_agent.filesystem'][str(audit.parent/'perception_host')],'none')

    def test_unsupported_module_cannot_silently_fall_back(self):
        with self.assertRaises(ValueError):validate_settings(dict(mode='sam_depth_not_installed'))
        with self.assertRaises(ValueError):validate_settings(dict(mode='sam_raw_depth'))

    def test_prompt_mention_is_not_measurement_visibility_evidence(self):
        self.assertFalse(has_measurement({'text':'Some conditions attach perception_evidence.'}))

    def test_measurement_in_codex_tool_output_survives_truncation_notice(self):
        value={'text':'Warning: truncated output\n{"perception_evidence":{"frame":{"step_id":0}}}\nimage descriptor'}
        self.assertTrue(has_measurement(value))


if __name__=='__main__':unittest.main()
