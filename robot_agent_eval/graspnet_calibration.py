"""Read-only native reachability of real Contact-GraspNet candidates.

Panda base -> contact centre uses the source gripper flat-pad Z=.1034m;
ARX link6 -> contact centre uses the independently declared .145m X bias.
No trajectory, contact compatibility or robot task success is asserted.
"""
import numpy as np
from scipy.spatial.transform import Rotation
from .common import ROOT,read,write,sha
from .ablation_perception import GRASP_BIAS_M,LINK_TO_TCP_ROTATION,load_recorded_camera


def contact_grasp_to_link(matrix, *, pregrasp_m=0.):
    matrix=np.asarray(matrix,float)
    if matrix.shape!=(4,4) or not np.isfinite(matrix).all():raise ValueError('Invalid learned grasp pose')
    Rtcp=matrix[:3,:3]
    if not np.allclose(Rtcp.T@Rtcp,np.eye(3),atol=1e-4) or np.linalg.det(Rtcp)<.99:
        raise ValueError('Invalid learned rotation')
    center=matrix[:3,3]+(.1034-pregrasp_m)*Rtcp[:,2]
    Rlink=Rtcp@LINK_TO_TCP_ROTATION.T
    position=center-Rlink@np.array([GRASP_BIAS_M,0,0])
    q=Rotation.from_matrix(Rlink).as_quat()
    return [*position.tolist(),float(q[3]),*q[:3].tolist()],center.tolist()


def run(env,args,config):
    probe=ROOT/'results/contact-graspnet-probe-20261013'
    identity=read(probe/'identity.json');origin=load_recorded_camera(identity['frame'])
    camera=env.observation['vision']['cam_head']
    for field in ('depth','intrinsic_matrix','extrinsic_matrix'):
        if not np.array_equal(np.asarray(origin[field]),np.asarray(camera[field])):
            raise ValueError('Recorded candidates require identical current depth/calibration')
    rows=[]
    with np.load(probe/'candidates.npz',allow_pickle=False) as data:
        for index,(pose,score,width) in enumerate(zip(data['world_poses'],data['scores'],data['predicted_openings_m'])):
            row=dict(index=index,score=float(score),predicted_opening_m=float(width),arms={})
            for arm in ('left','right'):
                poses={}
                for stage,clearance in (('pregrasp',.09),('grasp',0.)):
                    link,center=contact_grasp_to_link(pose,pregrasp_m=clearance)
                    ik=env.solve_pose(arm,link)
                    ik={k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in ik.items()}
                    poses[stage]=dict(link_pose=link,contact_center_xyz=center,ik=ik,
                                      reachable=ik.get('status')=='Success')
                row['arms'][arm]=poses
            rows.append(row)
    write(args.output/'graspnet_reachability.json',dict(candidates=rows,
        candidates_sha256=sha(probe/'candidates.npz'),source_identity=identity,
        reachable_both_stages=sum(any(all(p['reachable'] for p in stages.values()) for stages in r['arms'].values()) for r in rows),
        panda_pad_center_offset_m=.1034,arx_link6_tcp_offset_m=.145,
        native_steps=env.tick,scope='Static IK only; no trajectory/collision sweep, width adaptation, contact or grasp success test'))
