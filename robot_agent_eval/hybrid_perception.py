"""Add public perception evidence to Astra's original hybrid, without actions.

The original Astra gate, pi05 input, action schema and executor stay in charge.
Raw sensor records live in a host-only directory; only the configured supplement
is attached to Astra's observation/proposal packets. No semantic seed replay.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import subprocess
import time
import urllib.request
import numpy as np
from PIL import Image
from .common import ROOT, read, write, sha
from .ablation_perception import camera_contract, backproject, load_recorded_camera, LocalSAM

MODES = ('none', 'raw_depth', 'sam_raw_depth', 'sam_lingbot_depth')
COMMON_NOTE = (
    'This is a paired perception experiment. You remain the autonomous Astra '
    'hybrid policy: schedule every infer/execute cycle, assess the original gate, '
    'and author every edit or EEF correction. Some conditions attach '
    'perception_evidence, others do not. These are fallible measurements, never '
    'object truth or action commands. A mask centroid is not a grasp target. '
    'Check observation step IDs, units, camera conventions and current RGB. '
    'Do not declare success from these estimates. Do not change the existing '
    'action limits or bypass the rollout tools. In public decision reasons, '
    'briefly state whether a measurement affected the decision when relevant.'
)


def validate_settings(settings):
    if settings['mode'] not in MODES:
        raise ValueError('Unsupported perception condition')
    if settings['mode'].startswith('sam_') and not settings.get('target_text'):
        raise ValueError('SAM condition requires a public task-derived target description')
    if settings.get('camera', 'cam_head') != 'cam_head':
        raise ValueError('Initial experiment supports the head camera only')
    return settings


def depth_evidence(camera, rows=8, cols=12):
    """Same finite samples/grid in every depth-enabled condition."""
    depth, K, T = camera_contract(camera)
    h, w = depth.shape
    samples = []
    for r in range(rows):
        for c in range(cols):
            uv = [int((r+.5)*h/rows), int((c+.5)*w/cols)]
            value = depth[tuple(uv)]
            valid = bool(np.isfinite(value) and value > 0)
            samples.append(dict(pixel_rc=uv, depth_m=round(float(value), 4) if valid else None))
    return dict(image_shape_hw=[h,w], grid_shape=[rows,cols], samples=samples,
        intrinsic_matrix=K.tolist(), camera_to_world_usd=T.tolist(),
        convention='Pixels [row,col]; optical axial depth in meters; USD camera-to-world (+Y up, -Z forward)',
        valid_fraction=float(np.mean(np.isfinite(depth) & (depth > 0))))


def segment_evidence(camera, mask, receipt, target_text):
    depth, _, _ = camera_contract(camera)
    uv = np.argwhere(mask)
    if len(uv) < 20:
        raise ValueError('Insufficient segmented pixels')
    valid = mask & np.isfinite(depth) & (depth > 0)
    pixels = np.argwhere(valid)
    if len(pixels) < 20:
        raise ValueError('Insufficient segmented depth')
    xyz = backproject(camera, pixels)
    center = np.median(xyz, axis=0)
    _, singular, axes = np.linalg.svd(xyz-center, full_matrices=False)
    return dict(target_text=target_text, detector_score=receipt['score'],
        bbox_rc=[uv.min(0).tolist(), uv.max(0).tolist()], mask_pixels=len(uv),
        valid_depth_pixels=len(pixels), depth_valid_fraction=len(pixels)/len(uv),
        visible_surface_median_world_xyz=center.tolist(),
        visible_surface_world_bounds_p05_p95=np.percentile(xyz,[5,95],axis=0).tolist(),
        surface_principal_axes_world=axes.tolist(), singular_values=singular.tolist(),
        interpretation='Visible surface geometry only; centroid is not a grasp point; PCA axes do not specify a gripper pose')


class PerceptionModels:
    def __init__(self, settings, output):
        self.settings=validate_settings(settings); self.output=Path(output)
        self.sam=self.depth_model=None
        mode=settings['mode'];before=time.perf_counter()
        identity=dict(mode=mode,source_sha256=sha(Path(__file__)))
        if mode.startswith('sam_'):
            self.sam=LocalSAM(ROOT/'checkpoints/sam3/sam3.pt')
            identity['sam']=read(ROOT/'results/sam3-download.json')
        if mode=='sam_lingbot_depth':
            import sys, torch
            source=read(ROOT/'results/lingbot-depth-source.json')
            weights=read(ROOT/'results/lingbot-depth-download.json')
            if not source['complete'] or not weights['complete']:
                raise ValueError('LingBot source/checkpoint verification incomplete')
            sys.path.insert(0,str(ROOT/'.deps/lingbot'))
            sys.path.insert(0,str(ROOT/'runtime-sources/lingbot-depth'))
            import xformers
            from mdm.model.v2 import MDMModel
            with torch.autocast('cuda',enabled=False):
                self.depth_model=MDMModel.from_pretrained(ROOT/'checkpoints/lingbot-depth-v0.5/model.pt').eval().cuda()
            identity['lingbot']=dict(source=source,checkpoint=weights,
                resolution_level=settings.get('lingbot_resolution_level',0),
                runtime=dict(torch=torch.__version__,xformers=xformers.__version__,
                    xformers_install='isolated .deps/lingbot, --no-deps; existing torch retained'))
        identity['load_s']=time.perf_counter()-before
        write(self.output/'model_identity.json',identity)

    def refine(self, camera, directory):
        import torch
        depth,K,_=camera_contract(camera); h,w=depth.shape
        rgb=np.asarray(camera['color'],np.float32)/255.
        original_valid=np.isfinite(depth) & (depth > 0)
        inputs=np.where(original_valid,depth,0).astype(np.float32)
        normalized=K.copy(); normalized[0]/=w; normalized[1]/=h
        torch.cuda.synchronize();before=time.perf_counter()
        with torch.inference_mode(),torch.autocast('cuda',enabled=False):
            result=self.depth_model.infer(torch.from_numpy(rgb).permute(2,0,1).unsqueeze(0).cuda(),
                depth_in=torch.from_numpy(inputs).unsqueeze(0).cuda(),
                intrinsics=torch.tensor(normalized,dtype=torch.float32,device='cuda').unsqueeze(0),
                resolution_level=self.settings.get('lingbot_resolution_level',0))
        torch.cuda.synchronize();elapsed=time.perf_counter()-before
        predicted=result['depth'].squeeze(0).cpu().numpy()
        if predicted.shape!=depth.shape:raise ValueError('LingBot output depth shape differs from sensor')
        np.save(directory/'lingbot_depth.npy',predicted)
        refined=deepcopy(camera)
        refined['depth']=predicted;refined['distance_to_image_plane']=predicted
        return refined,dict(inference_s=elapsed,source='LingBot-Depth-v0.5 RGB+raw-depth refinement',
            input_valid_fraction=float(original_valid.mean()),
            output_valid_fraction=float(np.mean(np.isfinite(predicted) & (predicted>0))),
            raw_depth_sha256=sha(directory/'public_rgbd.npz'),output_sha256=sha(directory/'lingbot_depth.npy'))

    def measure(self, directory):
        directory=Path(directory);camera=load_recorded_camera(directory)
        before=time.perf_counter();mode=self.settings['mode']
        evidence=dict(mode=mode,frame=read(directory/'frame.json'),objects=[],errors=[],
            source='Current public sensor input; no layout/reward/object-state access',
            no_action_generated=True,metric_geometry=True)
        if mode=='sam_lingbot_depth':
            camera,evidence['depth_refinement']=self.refine(camera,directory)
        if mode!='none':evidence['depth_grid']=depth_evidence(camera)
        if mode.startswith('sam_'):
            try:
                mask,receipt=self.sam.segment(camera['color'],text=self.settings['target_text'])
                Image.fromarray(mask.astype(np.uint8)*255).save(directory/'mask.png')
                obj=segment_evidence(camera,mask,receipt,self.settings['target_text'])
                obj['sam_inference_s']=receipt['elapsed_s'];evidence['objects'].append(obj)
                overlay=np.asarray(camera['color'],np.uint8).copy()
                overlay[mask]=(.55*overlay[mask]+.45*np.array([255,0,0])).astype(np.uint8)
                Image.fromarray(overlay).save(directory/'overlay.png')
                evidence['overlay_path']=str(directory/'overlay.png')
            except ValueError as error:
                # A negative result is returned to Astra; no seed replay,
                # fabricated target, threshold lowering or geometric fallback.
                evidence['errors'].append(dict(stage='target_segmentation',error=str(error)))
        evidence['elapsed_s']=time.perf_counter()-before
        write(directory/'evidence.json',evidence)
        return evidence


def serve(args):
    settings=read(args.config)['hybrid_perception'];args.output.mkdir(parents=True,exist_ok=True)
    models=PerceptionModels(settings,args.output)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            try:
                data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                directory=Path(data['directory']).resolve()
                if not directory.is_relative_to(args.output.resolve()):raise ValueError('Frame outside owned worker root')
                result=models.measure(directory)
                body=json.dumps(result,allow_nan=False).encode();self.send_response(200)
            except Exception as error:
                body=json.dumps(dict(error_type=type(error).__name__,error=str(error))).encode();self.send_response(500)
            self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
    server=HTTPServer(('127.0.0.1',args.port),Handler)
    write(args.output/'ready.json',dict(port=args.port))
    server.serve_forever()


def install(module, config):
    """Install an additive adapter around pinned upstream rollout methods."""
    settings=validate_settings(config['hybrid_perception'])
    original=module.RoboDojoTools
    original_turn=module.CodexPolicy._turn
    def common_turn(self,text):
        return original_turn(self,COMMON_NOTE+'\n\n'+text)
    module.CodexPolicy._turn=common_turn

    class EvidenceHybrid(original):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            self.perception_process=None;self.perception_log=None;self.evidence=None

        def _observation(self,directory,**kwargs):
            packet=super()._observation(directory,**kwargs)
            # All paired arms capture the same public sensor fields. Off arm
            # retains them only in the host-only tree, inaccessible to Astra.
            public=self._rpc('public_observation')
            if public['step']!=self.tick:raise ValueError('Perception observation version mismatch')
            frame=self.output/'perception_host'/f'{self.tick:04d}'
            frame.mkdir(parents=True,exist_ok=False)
            camera=public['vision']['cam_head'];camera_contract(camera)
            Image.fromarray(np.asarray(camera['color'],np.uint8)[...,:3]).save(frame/'cam_head.png')
            arrays={}
            for key in ('depth','distance_to_image_plane','intrinsic_matrix','extrinsic_matrix'):
                if camera.get(key) is not None:arrays['cam_head_'+key]=np.asarray(camera[key])
            np.savez_compressed(frame/'public_rgbd.npz',**arrays)
            write(frame/'frame.json',dict(episode_id=self.episode,step_id=self.tick,instruction=public['instruction'],
                teacher_rgb_exact_match=bool(np.array_equal(public['vision']['cam_head']['color'],self.obs['cam_high']))))
            if settings['mode']=='none':return packet
            if self.perception_process is None:
                import socket,os
                with socket.socket() as s:s.bind(('127.0.0.1',0));self.perception_port=s.getsockname()[1]
                self.perception_log=(self.output/'perception_host/worker.log').open('w')
                command=[str(ROOT/'.venvs/frameworks/bin/python'),'-m','robot_agent_eval.hybrid_perception','serve',
                    '--config',os.environ['ROBOT_EVAL_MODEL_CONFIG'],'--output',str(self.output/'perception_host'),
                    '--port',str(self.perception_port)]
                self.perception_process=subprocess.Popen(command,cwd=ROOT,stdout=self.perception_log,stderr=subprocess.STDOUT)
                deadline=time.monotonic()+180
                while not (self.output/'perception_host/ready.json').exists():
                    if self.perception_process.poll() is not None:raise RuntimeError('Perception worker failed to start')
                    if time.monotonic()>deadline:raise TimeoutError('Perception worker load timeout')
                    time.sleep(.2)
            before=time.perf_counter()
            request=urllib.request.Request(f'http://127.0.0.1:{self.perception_port}/measure',
                data=json.dumps(dict(directory=str(frame))).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=90) as response:self.evidence=json.load(response)
            self.evidence['ipc_measurement_wall_s']=time.perf_counter()-before
            overlay=self.evidence.pop('overlay_path',None)
            if overlay:
                import shutil
                path=directory/'perception_overlay.png';shutil.copy2(overlay,path)
                packet['images'].append(dict(camera='cam_head_sam_overlay',path=str(path)))
            packet['perception_evidence']=self.evidence
            write(directory/'perception_evidence.json',self.evidence)
            module.write_json(self.observation_path,packet)
            return packet

        def infer(self,**arguments):
            packet=super().infer(**arguments)
            if self.evidence is not None:
                packet['perception_evidence']=self.evidence
                module.write_json(Path(arguments['output_dir'])/'proposal.json',packet)
            return packet

        def close(self):
            try:super().close()
            finally:
                if self.perception_process is not None:
                    self.perception_process.terminate()
                    try:self.perception_process.wait(timeout=10)
                    except subprocess.TimeoutExpired:self.perception_process.kill();self.perception_process.wait()
                if self.perception_log:self.perception_log.close()
    module.RoboDojoTools=EvidenceHybrid


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['serve','recorded'])
    parser.add_argument('--config',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--port',type=int);parser.add_argument('--frame',type=Path)
    args=parser.parse_args()
    if args.command=='serve':serve(args)
    else:
        settings=read(args.config)['hybrid_perception']
        args.output.mkdir(parents=True,exist_ok=False)
        models=PerceptionModels(settings,args.output)
        import shutil
        d=args.output/'frame';shutil.copytree(args.frame,d)
        write(d/'frame.json',dict(recorded=True,instruction=read(d/'state.json')['instruction']))
        result=models.measure(d);print(json.dumps(result,allow_nan=False))


if __name__=='__main__':main()
