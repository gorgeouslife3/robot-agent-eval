"""Download authorized official SAM3 and verify its LFS digest without logging credentials."""
import hashlib,json,os
from pathlib import Path
import time
import requests
ROOT=Path(__file__).resolve().parents[1]
token=(ROOT/'secrets/hf-token').read_text().strip()
session=requests.Session()
# requests honors HTTP_PROXY / HTTPS_PROXY when configured by the operator.
headers={'Authorization':'Bearer '+token}
result={'repository':'facebook/sam3','complete':False,'files':{}}
try:
 info=session.get('https://huggingface.co/api/models/facebook/sam3?blobs=true',headers=headers,timeout=30);info.raise_for_status();info=info.json()
 result['revision']=info['sha']
 for filename in ('config.json','sam3.pt'):
  meta=next(f for f in info['siblings'] if f['rfilename']==filename);target=ROOT/'checkpoints/sam3'/filename
  target.parent.mkdir(parents=True, exist_ok=True)
  tmp=target.with_suffix(target.suffix+'.partial');resume=tmp.stat().st_size if tmp.exists() else 0
  h=dict(headers)
  if resume:h['Range']=f'bytes={resume}-'
  reply=session.get(f'https://huggingface.co/facebook/sam3/resolve/{info["sha"]}/{filename}',headers=h,stream=True,timeout=(30,90));reply.raise_for_status()
  if reply.status_code!=206:resume=0
  before=time.monotonic();last=before;total=resume
  with tmp.open('ab' if resume else 'wb') as f:
   for chunk in reply.iter_content(8*1024*1024):
    f.write(chunk);total+=len(chunk)
    if time.monotonic()-last>20:
     print(json.dumps({'file':filename,'downloaded_bytes':total}),flush=True);last=time.monotonic()
  digest=hashlib.sha256()
  with tmp.open('rb') as f:
   for block in iter(lambda:f.read(8*1024*1024),b''):digest.update(block)
  expected=meta.get('lfs',{}).get('sha256');checksum=digest.hexdigest()
  if expected and expected!=checksum:raise RuntimeError('LFS checksum mismatch')
  if meta.get('size') and total!=meta['size']:raise RuntimeError('File size mismatch')
  tmp.rename(target);result['files'][filename]={'path':str(target),'sha256':checksum,'expected_lfs_sha256':expected,'bytes':total,'elapsed_s':time.monotonic()-before}
  print(json.dumps({'verified':filename,'bytes':total,'sha256':checksum}),flush=True)
 result['complete']=True
except Exception as e:
 result['error_type']=type(e).__name__
 if isinstance(e,requests.HTTPError):result['http_status']=e.response.status_code
 print(json.dumps({'complete':False,'error_type':type(e).__name__}),flush=True)
finally:
 (ROOT/'results/sam3-download.json').write_text(json.dumps(result,indent=2)+'\n')
