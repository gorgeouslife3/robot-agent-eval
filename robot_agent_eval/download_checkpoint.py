"""Download the official ModelScope mirror; verify every file against local HF LFS IDs."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
from pathlib import Path
import time
import urllib.parse
import urllib.request
from .common import ROOT,read,write


def main():
    rows=read(ROOT/'checkpoint-download-manifest.json')
    destination=ROOT/'checkpoints';destination.mkdir(exist_ok=True)
    def fetch(row):
        path=destination/row['path'];path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists() and path.stat().st_size==row['size']:
            with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            if digest==row['sha256']:return dict(row,status='verified_cached')
        url='https://modelscope.cn/api/v1/datasets/RoboDojo-Benchmark/RoboDojo/repo?'+urllib.parse.urlencode(
            {'Revision':'master','FilePath':row['path']})
        start=time.perf_counter();temporary=path.with_suffix(path.suffix+'.download')
        digest=hashlib.sha256();size=0
        with urllib.request.urlopen(url,timeout=90) as response,temporary.open('wb') as stream:
            while block:=response.read(8*1024*1024):
                digest.update(block);stream.write(block);size+=len(block)
        if size!=row['size'] or digest.hexdigest()!=row['sha256']:
            raise ValueError('Official mirror differs from pinned LFS object: '+row['path'])
        temporary.replace(path)
        return dict(row,status='verified_download',elapsed_s=time.perf_counter()-start)
    result=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(fetch,row):row for row in rows}
        for future in as_completed(futures):
            try:value=future.result()
            except Exception as error:value=dict(futures[future],status='download_error',error=str(error))
            result.append(value);write(ROOT/'checkpoint-download-result.json',dict(files=result,
                expected=len(rows),complete=len(result)==len(rows) and all(v['status'].startswith('verified') for v in result)))
            print(value['path'].rsplit('/',1)[-1]+': '+value['status'],flush=True)


if __name__=='__main__':main()
