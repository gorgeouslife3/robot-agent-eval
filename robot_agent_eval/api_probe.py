"""One real Responses request, with no credential logging or model fallback."""
import argparse
import json
import time
import urllib.request
from .common import ROOT, key, read, write


def probe(config, output):
    if config['wire_api'] != 'responses' or config.get('allow_model_fallback'):
        raise ValueError('Expected fixed Responses provider')
    payload = dict(model=config['model'], input='Reply with exactly READY.',
                   reasoning={'effort':config['reasoning_effort']}, max_output_tokens=2048,
                   store=False)
    started = time.perf_counter()
    request = urllib.request.Request(config['base_url'].rstrip('/')+'/responses',
        data=json.dumps(payload).encode(), headers={'Authorization':'Bearer '+key(config),
                                                   'Content-Type':'application/json'})
    record = dict(model_requested=config['model'], base_url=config['base_url'],
                  purpose='connection_only_not_robot_evaluation')
    try:
        with urllib.request.urlopen(request, timeout=config['request_timeout_s']) as reply:
            response = json.load(reply)
        record.update(status=response.get('status'), model_returned=response.get('model'),
                      usage=response.get('usage'), response_id=response.get('id'),
                      text=''.join(c.get('text','') for o in response.get('output',[])
                                   if o.get('type')=='message' for c in o.get('content',[])
                                   if c.get('type')=='output_text'))
        record['ok'] = record['status']=='completed' and record['model_returned']==config['model']
    except Exception as error:
        record.update(ok=False, error_type=type(error).__name__, error=str(error))
    record['elapsed_s']=time.perf_counter()-started
    write(output, record)
    print(json.dumps(record, ensure_ascii=False))
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--config',type=str,default=str(ROOT/'configs/model.local.json'))
    p.add_argument('--output',type=str,default=str(ROOT/'api-preflight.json'))
    a=p.parse_args(); raise SystemExit(0 if probe(read(a.config),a.output)['ok'] else 1)
