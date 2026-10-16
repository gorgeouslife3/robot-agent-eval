"""Public RGB-D geometry shared by perception and manipulation ablations.

Pixels are [row, col], depth is optical-axis metres, native extrinsics are
USD camera-to-world (+Y up, -Z forward). No scene/layout truth is read here.
"""
from __future__ import annotations

import base64
import io
from pathlib import Path
import time
import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation

GRASP_BIAS_M = .145
# Canonical TCP: Z forward, X jaw closing; link6: X forward, Y closing.
LINK_TO_TCP_ROTATION = np.array([[0, 0, 1], [1, 0, 0], [0, 1, 0]], float)


def camera_contract(camera):
    depth = camera.get('distance_to_image_plane')
    if depth is None:
        depth = camera.get('depth')
    depth = np.asarray(depth, float).squeeze()
    K = np.asarray(camera['intrinsic_matrix'], float)
    T = np.asarray(camera['extrinsic_matrix'], float)
    if depth.ndim != 2 or K.shape != (3, 3) or T.shape != (4, 4):
        raise ValueError('Invalid RGB-D/calibration shapes')
    if not np.isfinite(K).all() or not np.isfinite(T).all() or K[0, 0] <= 0 or K[1, 1] <= 0:
        raise ValueError('Invalid camera calibration')
    if not np.allclose(T[3], [0, 0, 0, 1]) or not np.allclose(T[:3, :3].T @ T[:3, :3], np.eye(3), atol=1e-5):
        raise ValueError('Camera transform is not rigid')
    return depth, K, T


def backproject(camera, pixels, depths=None):
    depth, K, T = camera_contract(camera)
    uv = np.asarray(pixels, float).reshape(-1, 2)
    if not np.isfinite(uv).all() or np.any(uv < 0) or np.any(uv >= np.array(depth.shape)):
        raise ValueError('Pixel outside depth image')
    d = depth[uv[:, 0].astype(int), uv[:, 1].astype(int)] if depths is None else np.asarray(depths, float).reshape(-1)
    if len(d) != len(uv) or np.any(~np.isfinite(d) | (d <= 0)):
        raise ValueError('Invalid optical-axis depth')
    xyz = np.column_stack(((uv[:, 1]-K[0, 2])/K[0, 0]*d,
                           -(uv[:, 0]-K[1, 2])/K[1, 1]*d, -d))
    return xyz @ T[:3, :3].T + T[:3, 3]


def project(camera, points):
    _, K, T = camera_contract(camera)
    xyz = (np.asarray(points, float).reshape(-1, 3)-T[:3, 3]) @ T[:3, :3]
    d = -xyz[:, 2]
    if np.any(d <= 0):
        raise ValueError('Point behind camera')
    return np.column_stack((K[1, 2]-xyz[:, 1]/d*K[1, 1], K[0, 2]+xyz[:, 0]/d*K[0, 0])), d


def locate(camera, pixel, *, mask=None, estimator='point', radius_px=7):
    depth, _, _ = camera_contract(camera)
    raw = np.asarray(pixel, float)
    if raw.shape != (2,) or not np.isfinite(raw).all():
        raise ValueError('Expected finite [row,col]')
    row, col = np.rint(raw).astype(int)
    if not (0 <= row < depth.shape[0] and 0 <= col < depth.shape[1]):
        raise ValueError('Seed pixel outside image')
    if mask is not None and np.asarray(mask).shape != depth.shape:
        raise ValueError('Mask/depth shape mismatch')
    if estimator == 'point':
        uv = np.array([[row, col]])
        d = np.array([depth[row, col]])
    elif estimator in ('median', 'cloud'):
        rr, cc = np.indices(depth.shape)
        region = (rr-row)**2+(cc-col)**2 <= radius_px**2
        if mask is not None:
            region &= np.asarray(mask, bool)
        region &= np.isfinite(depth) & (depth > 0)
        uv = np.argwhere(region)
        if len(uv) < 5:
            raise ValueError('Insufficient valid target depth')
        d = depth[region]
        # Reject background/discontinuity depths without inventing replacements.
        median = np.median(d)
        good = np.abs(d-median) <= .025
        uv, d = uv[good], d[good]
        if len(d) < 5:
            raise ValueError('Insufficient target depth after rejection')
        if estimator == 'median':
            uv, d = np.array([[row, col]]), np.array([np.median(d)])
    else:
        raise ValueError('Unknown geometry estimator')
    xyz = backproject(camera, uv, d)
    return dict(world_xyz=np.median(xyz, axis=0).tolist(), depth_m=float(np.median(d)),
                valid_points=len(xyz), pixel=[int(row), int(col)], estimator=estimator)


def fit_target(camera, mask, seed_pixel, *, radius_m=.035):
    """Fit local target geometry around the semantic grasp point, not full centroid."""
    seed = locate(camera, seed_pixel, mask=mask, estimator='median')
    depth, _, _ = camera_contract(camera)
    valid = np.asarray(mask, bool) & np.isfinite(depth) & (depth > 0)
    cloud = backproject(camera, np.argwhere(valid))
    origin = np.array(seed['world_xyz'])
    local = cloud[np.linalg.norm(cloud-origin, axis=1) < radius_m]
    if len(local) < 10:
        raise ValueError('Too few local target points')
    center = np.median(local, axis=0)
    _, singular, axes = np.linalg.svd(local-center, full_matrices=False)
    axis = axes[0]
    axis[2] = 0
    if np.linalg.norm(axis) < .1:
        raise ValueError('Target axis is not a supported tabletop axis')
    axis /= np.linalg.norm(axis)
    return dict(**seed, local_center_xyz=center.tolist(), axis_world=axis.tolist(),
                singular_values=singular.tolist(), local_points=len(local)), cloud


def top_down_link_pose(target_xyz, axis_world, clearance_m=0.):
    axis = np.asarray(axis_world, float)
    axis[2] = 0
    if np.linalg.norm(axis) < 1e-6:
        raise ValueError('Degenerate closing direction')
    axis /= np.linalg.norm(axis)
    z = np.array([0., 0., -1.])
    x = np.cross(axis, z)  # close perpendicular to target's long axis
    tcp_R = np.column_stack((x, np.cross(z, x), z))
    link_R = tcp_R @ LINK_TO_TCP_ROTATION.T
    center = np.asarray(target_xyz, float) + [0, 0, clearance_m]
    link_xyz = center-link_R @ [GRASP_BIAS_M, 0, 0]
    q = Rotation.from_matrix(link_R).as_quat()
    return dict(position=link_xyz.tolist(), quaternion_wxyz=[float(q[3]), *q[:3].tolist()])


def tcp_position(link_pose):
    q = link_pose['quaternion_wxyz']
    R = Rotation.from_quat([*q[1:], q[0]]).as_matrix()
    return np.asarray(link_pose['position']) + R @ [GRASP_BIAS_M, 0, 0]


class LocalSAM:
    def __init__(self, checkpoint):
        import sys
        from .common import ROOT
        sys.path.insert(0, str(ROOT/'source-snapshots/rpent'))
        from rpent.robots.components.sam3_server import Sam3Facade
        before = time.perf_counter()
        self.facade = Sam3Facade(str(checkpoint))
        self.load_s = time.perf_counter()-before

    def segment(self, rgb, *, point=None, text=None, threshold=.2):
        stream = io.BytesIO()
        Image.fromarray(np.asarray(rgb, np.uint8)[..., :3]).save(stream, format='PNG')
        before = time.perf_counter()
        result = self.facade.segment(base64.b64encode(stream.getvalue()).decode(),
                                     point=point, text_prompt=text, min_score=threshold)
        elapsed = time.perf_counter()-before
        if not result['found']:
            raise ValueError('SAM target not found: '+str(result.get('reason')))
        mask = np.asarray(Image.open(io.BytesIO(base64.b64decode(result.pop('mask_png_base64'))))) > 0
        return mask, dict(**result, elapsed_s=elapsed, mode='point' if point is not None else 'text')


def load_recorded_camera(directory, name='cam_head'):
    directory = Path(directory)
    with np.load(directory/'public_rgbd.npz', allow_pickle=False) as arrays:
        camera = {key: arrays[name+'_'+key] for key in
                  ('depth', 'distance_to_image_plane', 'intrinsic_matrix', 'extrinsic_matrix')
                  if name+'_'+key in arrays}
    camera['color'] = np.asarray(Image.open(directory/(name+'.png')).convert('RGB'))
    camera_contract(camera)
    return camera
