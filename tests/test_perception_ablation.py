import unittest
import numpy as np
from robot_agent_eval.ablation_perception import (
    backproject, project, locate, fit_target, top_down_link_pose, tcp_position)
from robot_agent_eval.graspnet_calibration import contact_grasp_to_link


def camera():
    return dict(depth=np.ones((11, 11)), intrinsic_matrix=np.array([[100., 0, 5], [0, 100, 5], [0, 0, 1]]),
                extrinsic_matrix=np.eye(4))


class PerceptionAblationTests(unittest.TestCase):
    def test_usd_optical_axes_and_world_translation(self):
        c = camera(); c['extrinsic_matrix'][:3, 3] = [1, 2, 3]
        np.testing.assert_allclose(backproject(c, [[7, 8]]), [[1.03, 1.98, 2.]])

    def test_project_known_world_point(self):
        uv, depth = project(camera(), [[.03, -.02, -1]])
        np.testing.assert_allclose(uv, [[7, 8]])
        np.testing.assert_allclose(depth, [1])

    def test_invalid_depth_and_pixel_rejected(self):
        c = camera(); c['depth'][5, 5] = np.nan
        with self.assertRaises(ValueError): locate(c, [5, 5])
        with self.assertRaises(ValueError): locate(c, [-1, 5])
        with self.assertRaises(ValueError): locate(c, [5, 11])

    def test_mask_excludes_background(self):
        c = camera(); c['depth'][:] = 2.; c['depth'][5:7, 3:8] = 1.
        mask = c['depth'] == 1.
        estimate = locate(c, [5, 5], mask=mask, estimator='median')
        self.assertEqual(estimate['depth_m'], 1.)

    def test_empty_mask_cannot_manufacture_geometry(self):
        with self.assertRaises(ValueError):
            locate(camera(), [5, 5], mask=np.zeros((11, 11), bool), estimator='median')

    def test_local_axis_from_thin_strip(self):
        mask = np.zeros((11, 11), bool); mask[4:7, :] = True
        g, _ = fit_target(camera(), mask, [5, 5], radius_m=.1)
        self.assertGreater(abs(g['axis_world'][0]), .99)

    def test_top_down_pose_has_correct_tcp_offset(self):
        for axis in ([1., 0, 0], [0, 1., 0], [1., 1., 0]):
            p = top_down_link_pose([.3, -.1, .78], axis, .08)
            np.testing.assert_allclose(tcp_position(p), [.3, -.1, .86], atol=1e-10)
            self.assertAlmostEqual(p['position'][2], 1.005)

    def test_bad_calibration_rejected(self):
        c = camera(); c['extrinsic_matrix'][0, 0] = 2
        with self.assertRaises(ValueError): backproject(c, [[5, 5]])

    def test_graspnet_panda_origin_to_arx_contact_center(self):
        matrix=np.eye(4);matrix[:3,3]=[.3,-.1,.8]
        link,center=contact_grasp_to_link(matrix)
        np.testing.assert_allclose(center,[.3,-.1,.9034])
        np.testing.assert_allclose(tcp_position(dict(position=link[:3],quaternion_wxyz=link[3:])),center)

    def test_graspnet_pregrasp_retreats_opposite_approach(self):
        matrix=np.eye(4)
        _,center=contact_grasp_to_link(matrix,pregrasp_m=.09)
        np.testing.assert_allclose(center,[0,0,.0134])

    def test_graspnet_invalid_pose_rejected(self):
        matrix=np.eye(4);matrix[0,0]=2.
        with self.assertRaises(ValueError):contact_grasp_to_link(matrix)


if __name__ == '__main__': unittest.main()
