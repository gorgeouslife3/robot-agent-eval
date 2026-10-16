"""Real Contact-GraspNet checkpoint inference on recorded public RGB-D.

Generates camera/world candidates only: no robot execution, simulated geometry
or success labels. Upstream is the pinned third-party PyTorch implementation.
"""
import argparse
from pathlib import Path
import sys
import time
import numpy as np
from PIL import Image
from .common import ROOT,read,write,sha
from .ablation_perception import load_recorded_camera,camera_contract,backproject


def run(frame, mask_path, output):
    output.mkdir(parents=True,exist_ok=False)
    vendor=ROOT/'runtime-sources/contact_graspnet_pytorch'
    for path in (ROOT/'.deps/graspnet',vendor,vendor/'Pointnet_Pointnet2_pytorch'):
        sys.path.insert(0,str(path))
    model_path=vendor/'checkpoints/contact_graspnet/checkpoints/model.pt'
    config_path=model_path.parent.parent/'config.yaml'
    write(output/'identity.json',dict(source=read(ROOT/'results/contact-graspnet-source.json'),
        checkpoint_sha256=sha(model_path),config_sha256=sha(config_path),
        compatibility_patch_sha256=sha(ROOT/'source-snapshots/aspire/aspire/sim/patches/contact_graspnet_pytorch-compat.patch'),
        patched_files={n:sha(vendor/'contact_graspnet_pytorch'/n) for n in ('checkpoints.py','contact_graspnet.py','visualization_utils_o3d.py')},
        frame=str(frame.resolve()),rgbd_sha256=sha(frame/'public_rgbd.npz'),mask_sha256=sha(mask_path),
        condition='one actual forward pass, local regions/filter enabled, no synthetic viewpoint retries',
        candidate_frame='OpenCV optical camera, +Z forward; camera_to_world=USD extrinsics @ diag(1,-1,-1,1)',
        robot_execution=False))
    previous_tf32=None
    try:
        import torch
        import yaml
        from contact_graspnet_pytorch.contact_grasp_estimator import GraspEstimator
        from contact_graspnet_pytorch.checkpoints import CheckpointIO
        # SAM's tracking predictor keeps a CUDA BF16 autocast context entered.
        # PointNet neighbour search needs FP32 squared-distance arithmetic;
        # disabling TF32 alone does not override inherited autocast.
        previous_tf32=dict(matmul=torch.backends.cuda.matmul.allow_tf32,cudnn=torch.backends.cudnn.allow_tf32)
        torch.backends.cuda.matmul.allow_tf32=False
        torch.backends.cudnn.allow_tf32=False
        write(output/'numeric_runtime.json',dict(previous_tf32=previous_tf32,graspnet_tf32=False,
            inherited_cuda_autocast=torch.is_autocast_enabled('cuda'),
            inherited_cuda_autocast_dtype=str(torch.get_autocast_dtype('cuda')),
            graspnet_autocast=False,
            reason='Explicit FP32 neighbour search overrides SAM3 inherited BF16 autocast'))
        np.random.seed(0);torch.manual_seed(0)
        config=yaml.safe_load(config_path.read_text())
        config['OPTIMIZER']['batch_size']=1
        start=time.perf_counter()
        with torch.autocast(device_type='cuda',enabled=False):
            estimator=GraspEstimator(config)
            CheckpointIO(str(model_path.parent),model=estimator.model).load('model.pt')
            estimator.model.eval()
        torch.cuda.synchronize()
        load_s=time.perf_counter()-start
        camera=load_recorded_camera(frame)
        mask=np.asarray(Image.open(mask_path))>0
        depth,K,T=camera_contract(camera)
        if mask.shape!=depth.shape:raise ValueError('Mask/depth mismatch')
        uv=np.argwhere(np.isfinite(depth)&(depth>.2)&(depth<2.))
        world=backproject(camera,uv)
        Tcv=T@np.diag([1,-1,-1,1])
        full=(world-Tcv[:3,3])@Tcv[:3,:3]
        segment=full[mask[uv[:,0],uv[:,1]]]
        if len(segment)<20:raise ValueError('Not enough segmented points')
        start=time.perf_counter()
        with torch.inference_mode(), torch.autocast(device_type='cuda',enabled=False):
            grasps,scores,contacts,widths=estimator.predict_scene_grasps(full,pc_segments={1:segment},
                local_regions=True,filter_grasps=True,forward_passes=1)
        torch.cuda.synchronize()
        elapsed=time.perf_counter()-start
        poses=np.asarray(grasps.get(1,[]));conf=np.asarray(scores.get(1,[]));points=np.asarray(contacts.get(1,[]))
        openings=np.asarray(widths.get(1,[]))
        world_poses=Tcv@poses if len(poses) else np.empty((0,4,4))
        np.savez_compressed(output/'candidates.npz',camera_poses=poses,world_poses=world_poses,
            scores=conf,contact_points_camera=points,predicted_openings_m=openings)
        write(output/'result.json',dict(status='inference_completed',load_s=load_s,inference_s=elapsed,
            full_points=len(full),segment_points=len(segment),candidates=len(poses),
            max_score=float(conf.max()) if len(conf) else None,
            max_rotation_orthogonality_error=float(np.max(np.abs(np.swapaxes(poses[:,:3,:3],1,2)@poses[:,:3,:3]-np.eye(3)))) if len(poses) else None,
            scope='Actual learned grasp candidates; no IK/trajectory/robot success evaluation',
            gripper_frame='Contact-GraspNet Panda base origin; X closing/Z approach; TCP contact-center conversion required for ARX'))
    except Exception as error:
        write(output/'failure.json',dict(error_type=type(error).__name__,error=str(error)))
        raise
    finally:
        if previous_tf32 is not None:
            torch.backends.cuda.matmul.allow_tf32=previous_tf32['matmul']
            torch.backends.cudnn.allow_tf32=previous_tf32['cudnn']


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frame',type=Path,required=True);p.add_argument('--mask',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run(args.frame,args.mask,args.output)


if __name__=='__main__':main()
