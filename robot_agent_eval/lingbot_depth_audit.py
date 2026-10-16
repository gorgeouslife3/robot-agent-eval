"""Actual LingBot refinement on clean/degraded public depth; evaluator only.

The clean reference is never passed to a degraded-input inference. This is a
static, one-scene sensor audit, separate from Astra task success experiments.
"""
import argparse
from copy import deepcopy
from pathlib import Path
import time
import numpy as np
from PIL import Image
from .common import ROOT,read,write,sha
from .ablation_perception import load_recorded_camera,camera_contract
from .hybrid_perception import PerceptionModels


def statistics(predicted, reference, domain):
    valid=domain & np.isfinite(reference) & (reference>0) & np.isfinite(predicted) & (predicted>0)
    count=int(valid.sum());total=int(domain.sum())
    if not count:return dict(domain_points=total,valid_points=0,coverage=0,rmse_m=None,mae_m=None,absrel=None)
    error=predicted[valid]-reference[valid]
    return dict(domain_points=total,valid_points=count,coverage=count/max(1,total),
        rmse_m=float(np.sqrt(np.mean(error**2))),mae_m=float(np.mean(np.abs(error))),
        absrel=float(np.mean(np.abs(error)/reference[valid])),p95_abs_error_m=float(np.percentile(np.abs(error),95)))


def run(args):
    args.output.mkdir(parents=True,exist_ok=False)
    camera=load_recorded_camera(args.frame);clean,K,T=camera_contract(camera)
    target=np.asarray(Image.open(args.mask))>0
    if target.shape!=clean.shape:raise ValueError('Mask/depth mismatch')
    reference_valid=np.isfinite(clean)&(clean>0)
    models=PerceptionModels(dict(mode='sam_lingbot_depth',target_text='shovel',lingbot_resolution_level=0),args.output)
    rng=np.random.default_rng(41)
    random_holes=rng.random(clean.shape)<.3
    rr,cc=np.indices(clean.shape);block_holes=(rr>=215)&(rr<250)&(cc>=465)&(cc<495)
    noise=rng.normal(0,.01,clean.shape)
    rows=[]
    for corruption,level in (('clean',0),('clean',9),('random_holes_30pct',0),('shaft_block_hole',0),('gaussian_noise_10mm',0)):
        frame=args.output/(corruption+'-level'+str(level));frame.mkdir()
        observed=clean.copy()
        if corruption=='random_holes_30pct':observed[random_holes]=0
        elif corruption=='shaft_block_hole':observed[block_holes]=0
        elif corruption=='gaussian_noise_10mm':observed[reference_valid]+=noise[reference_valid]
        observed_camera=deepcopy(camera);observed_camera['depth']=observed;observed_camera['distance_to_image_plane']=observed
        np.savez_compressed(frame/'public_rgbd.npz',cam_head_depth=observed,cam_head_distance_to_image_plane=observed,
                            cam_head_intrinsic_matrix=K,cam_head_extrinsic_matrix=T)
        models.settings['lingbot_resolution_level']=level
        refined,receipt=models.refine(observed_camera,frame)
        predicted,*_=camera_contract(refined)
        missing=(~np.isfinite(observed)|(observed<=0))&reference_valid
        retained=reference_valid&~missing
        regions=dict(all_reference_valid=reference_valid,target_mask=target&reference_valid,
            missing=missing,retained=retained,target_missing=target&missing,target_retained=target&retained)
        metrics={key:dict(input=statistics(observed,clean,mask),refined=statistics(predicted,clean,mask))
                 for key,mask in regions.items()}
        row=dict(corruption=corruption,resolution_level=level,inference=receipt,metrics=metrics)
        write(frame/'metrics.json',row);rows.append(row);print(corruption,level,receipt['inference_s'],metrics['target_mask'],flush=True)
    write(args.output/'results.json',dict(rows=rows,random_seed=41,reference_rgbd_sha256=sha(args.frame/'public_rgbd.npz'),
        target_mask_sha256=sha(args.mask),scope='One public initial frame; clean rendered depth reference only; synthetic corruptions do not model a real sensor; no Astra task outcome',
        model_identity=read(args.output/'model_identity.json')))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frame',type=Path,required=True);p.add_argument('--mask',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    run(p.parse_args())


if __name__=='__main__':main()
