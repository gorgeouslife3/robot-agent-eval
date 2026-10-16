"""Loopback Responses gateway: count real model requests and keep keys host-side."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import urllib.request
import urllib.error
from .common import key


class ModelProxy:
    def __init__(self,config,output):
        self.config=config; self.secret=key(config); self.output=output
        # An empty initialized journal proves zero submitted calls; it must
        # not be confused with a legacy/missing accounting file.
        self.output.touch(exist_ok=True)
        self.output.with_name('model_request_starts.jsonl').touch(exist_ok=True)
        self.calls=0;self.lock=threading.Lock();self.started=None
        owner=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.0'
            def log_message(self,*args):pass
            def do_POST(self):
                if self.path not in ('/v1/responses','/responses'):
                    self.send_error(404);return
                payload=self.rfile.read(int(self.headers.get('Content-Length','0')))
                value=json.loads(payload)
                if value.get('model')!=owner.config['model']:
                    self.send_error(400,'Model differs from frozen configuration');return
                with owner.lock:
                    owner.calls+=1;call=owner.calls
                # Exact model-visible payload, with no HTTP credentials. This
                # makes prompt/skill provenance inspectable for all planners.
                payload_dir=owner.output.parent/'model_inputs';payload_dir.mkdir(exist_ok=True)
                (payload_dir/f'{call:03d}.json').write_text(json.dumps(value,ensure_ascii=False))
                before=time.perf_counter()
                record=dict(call=call,model=value['model'],stream=bool(value.get('stream')),
                            started_monotonic=before,reasoning=value.get('reasoning'),
                            request_bytes=len(payload))
                if call>owner.config['max_model_calls_per_episode']:
                    record.update(error='model_call_budget',elapsed_s=0)
                    owner.record(record);self.send_error(429,'Evaluation model-call budget exhausted');return
                # Persist submitted calls before waiting, so an interrupted
                # request does not disappear when this process exits.
                owner.record(dict(record, phase='upstream_request_submitted'), starts=True)
                request=urllib.request.Request(owner.config['base_url'].rstrip('/')+'/responses',
                    data=payload,headers={'Authorization':'Bearer '+owner.secret,'Content-Type':'application/json',
                        'Accept':self.headers.get('Accept','text/event-stream')})
                tail=b''
                try:
                    with urllib.request.urlopen(request,timeout=owner.config['request_timeout_s']) as reply:
                        self.send_response(reply.status)
                        self.send_header('Content-Type',reply.headers.get('Content-Type','application/json'))
                        self.end_headers()
                        for line in reply:
                            self.wfile.write(line);self.wfile.flush()
                            if value.get('stream') and line.startswith(b'data: '):
                                try:
                                    event=json.loads(line[6:])
                                    if event.get('type') in ('response.completed','response.incomplete','response.failed'):
                                        response=event['response']
                                        record.update(status=response.get('status'),usage=response.get('usage'),
                                                      model_returned=response.get('model'),response_id=response.get('id'))
                                except (ValueError,KeyError):pass
                            elif not value.get('stream'):tail+=line
                        if tail:
                            response=json.loads(tail);record.update(status=response.get('status'),usage=response.get('usage'),
                                model_returned=response.get('model'),response_id=response.get('id'))
                except urllib.error.HTTPError as error:
                    record.update(error_type='HTTPError',http_status=error.code)
                    self.send_error(error.code,'Upstream model request failed')
                except Exception as error:
                    record.update(error_type=type(error).__name__,error=str(error))
                finally:
                    record['elapsed_s']=time.perf_counter()-before;owner.record(record)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)

    def record(self,value,starts=False):
        with self.lock:
            path=self.output.with_name('model_request_starts.jsonl') if starts else self.output
            with path.open('a') as stream:stream.write(json.dumps(value)+'\n')

    def start(self):
        self.thread.start();return f'http://127.0.0.1:{self.server.server_port}/v1'

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
