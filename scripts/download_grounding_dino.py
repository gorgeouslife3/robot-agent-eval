"""Fetch GaP's declared detector from official HF, retaining file identities."""
import hashlib,json,time
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1];repo='IDEA-Research/grounding-dino-base'
s=requests.Session()  # Honors operator-configured HTTPS_PROXY.
result={'repository':repo,'complete':False,'files':{}}
try:
 r=s.get('https://huggingface.co/api/models/'+repo+'?blobs=true',timeout=30);r.raise_for_status();info=r.json();result['revision']=info['sha']
 dest=ROOT/'checkpoints/grounding-dino-base';dest.mkdir(exist_ok=True)
 for meta in info['siblings']:
  name=meta['rfilename']
  if '/' in name or not (name.endswith(('.json','.txt')) or name=='model.safetensors'):continue
  target=dest/name
  if target.exists() and target.stat().st_size==meta.get('size'):continue
  r=s.get(f'https://huggingface.co/{repo}/resolve/{info["sha"]}/{name}',stream=True,timeout=(30,90));r.raise_for_status()
  tmp=target.with_suffix(target.suffix+'.partial');digest=hashlib.sha256();total=0;last=time.monotonic()
  with tmp.open('wb') as f:
   for block in r.iter_content(8*1024*1024):
    f.write(block);digest.update(block);total+=len(block)
    if time.monotonic()-last>20:print(json.dumps({'file':name,'downloaded_bytes':total}),flush=True);last=time.monotonic()
  checksum=digest.hexdigest();expected=meta.get('lfs',{}).get('sha256')
  if expected and checksum!=expected:raise RuntimeError('Detector checksum mismatch')
  tmp.rename(target);result['files'][name]={'bytes':total,'sha256':checksum,'expected_lfs_sha256':expected}
  print(json.dumps({'verified':name,'bytes':total}),flush=True)
 result['complete']=True
except Exception as e:
 result['error_type']=type(e).__name__;print(json.dumps({'error_type':type(e).__name__}),flush=True)
finally:(ROOT/'results/grounding-dino-download.json').write_text(json.dumps(result,indent=2)+'\n')
