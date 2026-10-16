"""Compare two development trials; numerical differences do not establish cause."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image,ImageDraw
from robot_agent_eval.common import ROOT,read,write

names=('20261011-212157-619323-rpent_astra-general_pickup-l1','20261011-212848-178623-rpent_astra-general_pickup-l1')
runs=[ROOT/'runs'/n for n in names]
initial=[r/'controller/sensors/initial' for r in runs]
report=dict(runs=list(map(str,runs)),initial_images={},initial_state={},proposal_delta={},
    note='Sensor configuration changed between these trials. Same layout/initial proprioception does not imply bit-identical rendered frames. This is diagnostic evidence, not a controlled estimate of the cause of success.')
for cam in ('cam_head','cam_left_wrist','cam_right_wrist'):
    x,y=[np.asarray(Image.open(p/(cam+'.png'))).astype(float) for p in initial]
    report['initial_images'][cam]=dict(mean_abs_delta=float(np.abs(x-y).mean()),max_abs_delta=float(np.abs(x-y).max()),changed_channel_fraction=float((x!=y).mean()))
s,t=[read(p/'state.json')['state'] for p in initial]
for k in s:report['initial_state'][k]=float(np.abs(np.asarray(s[k])-np.asarray(t[k])).max())
for i in range(4):
    paths=[p/'controller'/f'policy_proposal_{i:03d}.npz' for p in runs]
    if not all(p.exists() for p in paths):break
    files=[np.load(p) for p in paths]
    report['proposal_delta'][str(i)]={}
    for k in files[0].files:
        x,y=[f[k] for f in files]
        if x.dtype.kind in 'fiu' and x.shape==y.shape:
            delta=np.abs(x.astype(float)-y.astype(float))
            report['proposal_delta'][str(i)][k]=dict(mean_abs=float(delta.mean()),max_abs=float(delta.max()))
write(ROOT/'results/rpent-repeat-observation-audit.json',report)
canvas=Image.new('RGB',(1280,1020),'white');d=ImageDraw.Draw(canvas)
for col,r in enumerate(runs):
    result=read(r/'result.json');step=result['native_steps']
    for row,(label,p) in enumerate((('Initial',r/'controller/sensors/initial/cam_head.png'),
        (f'Final recorded head: step {step}',r/'controller/sensors'/f'{step:04d}'/'cam_head.png'))):
        d.text((col*640+10,row*510+8),f'{label}; native success={result["native_success"]}',fill='black')
        canvas.paste(Image.open(p),(col*640,row*510+30))
canvas.save(ROOT/'results/rpent-repeat-head-frames.png')
print(ROOT/'results/rpent-repeat-observation-audit.json')
