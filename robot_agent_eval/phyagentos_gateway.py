"""Local Forge Tool API transport over real RoboDojo execution.

Uses the released PhyAgentOS BridgeState for official VLA decisions. Replaces
Dora transport only; no invented simulator outcome or segmentation is supplied.
"""
import base64
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import uuid
import sys
from urllib.parse import unquote
import numpy as np
import yaml
from .common import ROOT,write,read
from .framework_io import append_trace


class Gateway:
    def __init__(self,env,policy,args,custom):
        self.env=env;self.policy=policy;self.args=args;self.custom=custom;self.invocation=None;self.invocations={};self.batch_running=False
        self.lock=threading.RLock();self.capture_seq=0
        root=ROOT/'runtime-sources/phyagentos-robodojo-skill'
        # The released package __init__ eagerly imports its Dora CLI. Load the
        # unchanged state/config modules under a private package namespace so
        # a transport-only adapter does not require unrelated Dora carriers.
        import importlib
        from types import ModuleType
        package='_robodojo_official_bridge'
        if package not in sys.modules:
            module=ModuleType(package);module.__path__=[str(root/'nodes/vla_bridge/src/vla_bridge')]
            sys.modules[package]=module
        BridgeState=importlib.import_module(package+'.service').BridgeState
        labels=[f'{a}_{f}.{i}' for a in ('left','right') for f,n in (('arm_joint_state',6),('ee_joint_state',1)) for i in range(n)]
        self.bridge=BridgeState(policy_id='Pi_05',initial_mode='stop',policy_command_sender=lambda verb:uuid.uuid4().hex,
            proprio_gate='seen',max_segment_steps=10,joint_abs_labels=labels,gripper_indices=(6,13),
            checkpoints_enabled=True,accepted_modes=('student','edit','stop','policy','agent'),hold_on_episode_start=True)
        self.bridge.reset_episode();self.update_proprio()
        raw=yaml.safe_load((root/'profiles/gpt6_pi05/gateway.yaml').read_text())
        specs=raw.get('tools',{}).get('specs',[])
        if not specs:raise ValueError('Official gateway tool specs missing')
        self.specs={s['tool_id']:s for s in specs}
        if custom:
            from .react_harness import action_tool
            action=action_tool()
            self.specs={
                'robot.observe':dict(tool_id='robot.observe',endpoint_id='robot',operation='observe',semantics='query',
                    description='Read public RGB paths, measured arm poses and native control budget.',input_schema={'type':'object','properties':{}},output_schema={'type':'object'}),
                'robot.delta_action':dict(tool_id='robot.delta_action',endpoint_id='robot',operation='delta_action',semantics='action',
                    description=action['description'],input_schema=action['parameters'],output_schema={'type':'object'})}
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*a):pass
            def answer(self,code,data):
                encoded=json.dumps(data,ensure_ascii=False,default=lambda v:np.asarray(v).tolist()).encode()
                self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)
            def do_GET(self):self.handle_api('GET')
            def do_POST(self):self.handle_api('POST')
            def handle_api(self,method):
                payload=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or b'{}')
                path=unquote(self.path)
                with owner.lock:
                    before=time.perf_counter();start=owner.env.tick
                    try:
                        code,data=owner.dispatch(method,path,payload)
                        append_trace(owner.args.output,dict(event='forge_gateway',method=method,path=path,arguments=payload,
                            start_step=start,end_step=owner.env.tick,elapsed_s=time.perf_counter()-before))
                        self.answer(code,dict(ok=True,data=data))
                    except Exception as e:
                        append_trace(owner.args.output,dict(event='forge_gateway_error',method=method,path=path,arguments=payload,
                            start_step=start,end_step=owner.env.tick,elapsed_s=time.perf_counter()-before,error_type=type(e).__name__,error=str(e)))
                        self.answer(400,dict(ok=False,error=dict(code='LOCAL_ADAPTER_ERROR',message=str(e),retryable=False)))
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
    def update_proprio(self):
        s=self.env.get_obs()['state'];j=np.concatenate([np.r_[s[a+'_arm_joint_state'],s[a+'_ee_joint_state']] for a in ('left','right')])
        self.bridge.observe_proprio(joint_positions=j.tolist())
    def observation(self):
        self.env.get_obs();self.capture_seq+=1;name=f'forge-{self.capture_seq:04d}';self.env.save_observation(name)
        s=self.env.observation['state'];d=self.args.output/'sensors'/name
        return dict(instruction=self.env.observation['instruction'],step=self.env.tick,remaining_steps=200-self.env.tick,
            current_state={k:np.asarray(v).tolist() for k,v in s.items()},
            current_eef={a:dict(position=np.asarray(s[a+'_ee_pose'])[:3].tolist(),quaternion_wxyz=np.asarray(s[a+'_ee_pose'])[3:7].tolist(),
                gripper_opening_command=float(np.asarray(s[a+'_ee_joint_state']).ravel()[0])) for a in ('left','right')},
            images=[dict(camera=n,path=str(d/(n+'.png'))) for n in ('cam_head','cam_left_wrist','cam_right_wrist')],rollout_finished=self.env.ended)
    def dispatch(self,method,path,payload):
        if method=='GET' and path=='/tools':return 200,dict(tools=list(self.specs.values()))
        if method=='GET' and path.startswith('/tools/'):
            name=path[7:].removesuffix('/context');spec=self.specs[name]
            return 200,(dict(ready=True,binding_error=None,tool=spec) if path.endswith('/context') else spec)
        if method=='GET' and path.startswith('/invocations/'):
            identifier=path[13:].removesuffix('/result')
            if identifier not in self.invocations:raise ValueError('Unknown invocation')
            data=dict(self.invocations[identifier])
            if self.batch_running and identifier==self.invocation['invocation_id']:
                if self.env.ended:
                    data.update(status='succeeded',outputs=self.batch_result());self.invocation=data;self.invocations[identifier]=data;self.batch_running=False
                else:data.update(status='running')
            if path.endswith('/result'):
                if data['status']=='running':return 202,dict(status='pending')
                return 200,dict(status='available',result=dict(status=data['status'],outputs=data.get('outputs',{})))
            # AgentTaskCoordinator consumes phase/state for lifecycle snapshots,
            # and status=available/result for authoritative terminal results.
            return 200,dict(invocation_id=data['invocation_id'],attempt_id=data['attempt_id'],phase=data['status'])
        if method=='POST' and path.endswith(':invoke'):
            binding=path[7:-7]
            name=next((n for n,s in self.specs.items() if binding in (n,s['endpoint_id']+'/'+s['operation'])),None)
            if name is None:raise ValueError('Unregistered tool binding')
            args=payload.get('arguments',{})
            import jsonschema
            jsonschema.validate(args,self.specs[name]['input_schema'])
            if name=='bench.run':
                expected=dict(task_ids=[0],init_state_ids=[self.args.layout],num_runs=1,seed=0,max_steps=200)
                if args!=expected:raise ValueError('Only frozen single case is enabled: '+json.dumps(expected))
                if self.invocation:raise ValueError('Single-attempt batch already admitted')
                self.batch_running=True;self.invocation=dict(invocation_id='inv_'+uuid.uuid4().hex,attempt_id='attempt_'+uuid.uuid4().hex,status='running')
                self.invocations[self.invocation['invocation_id']]=self.invocation
                return 202,self.invocation
            if name=='robot.delta_action':
                if self.invocation and self.invocation['status']=='running':raise ValueError('An action is active')
                result=self.delta(args)
                self.invocation=dict(invocation_id='inv_'+uuid.uuid4().hex,attempt_id='attempt_'+uuid.uuid4().hex,status='succeeded',outputs=result)
                self.invocations[self.invocation['invocation_id']]=self.invocation
                return 202,dict(self.invocation,status='accepted')
            if name=='robot.observe':return 200,dict(status='succeeded',outputs=self.observation())
            if name=='bench.describe':return 200,dict(status='succeeded',outputs=dict(benchmark='RoboDojo',suite='general_pickup',policy_id='Pi_05',
                env_cfg_type='arx_x5',action_type='joint',num_tasks=1,tasks=[dict(task_id=0,name=self.args.task,language=self.env.get_task_language(),num_init_states=self.args.layout+1)],
                frozen_init_state_ids=[self.args.layout],defaults=dict(num_runs=1,seed=0,max_steps=200),limits=dict(max_total_episodes=1,max_max_steps=200)))
            if name=='vla.get_status':return 200,dict(status='succeeded',outputs=self.bridge.status(600000))
            if name=='vla.set_mode':
                if not self.batch_running:raise ValueError('Start bench.run before enabling policy forwarding')
                result=self.bridge.set_mode(**args);self.forward_policy()
                return 200,dict(status='succeeded',outputs=result)
            if name=='vla.decide':
                if not self.batch_running:raise ValueError('Start bench.run before deciding segments')
                result=self.bridge.decide(**args)
                self.forward_policy()
                return 200,dict(status='succeeded',outputs=result)
            if name.startswith('vision.get_frame'):
                obs=self.observation();camera={'vision.get_frame':'cam_head','vision.get_frame_left_wrist':'cam_left_wrist','vision.get_frame_right_wrist':'cam_right_wrist'}[name]
                item=next(x for x in obs['images'] if x['camera']==camera)
                from PIL import Image
                with Image.open(item['path']) as frame:width,height=frame.size
                return 200,dict(status='succeeded',outputs=dict(image_path=item['path'],frame_seq=self.capture_seq,frame_age_ms=0,width=width,height=height))
        raise ValueError('Unsupported local Gateway operation '+path)
    def forward_policy(self):
        while self.bridge.forwarding and not self.env.ended:
            actions=self.policy.predict(self.env.get_obs())
            for command in actions:
                if not self.bridge.forwarding or self.env.ended:break
                row=np.concatenate([np.r_[command[a+'_arm_joint_state'],command[a+'_ee_joint_state']] for a in ('left','right')]).tolist()
                self.bridge.observe_action(row);row,edited=self.bridge.shape_action(row)
                cmd={f'{a}_{f}':row[o:o+n] for a,b in (('left',0),('right',7)) for f,o,n in (('arm_joint_state',b,6),('ee_joint_state',b+6,1))}
                self.env.step(cmd);self.update_proprio();self.bridge.note_forwarded()
            if not actions:raise RuntimeError('Policy returned no actions')
        if self.env.ended:self.bridge.end_episode()
    def delta(self,args):
        from .react_harness import action_to_eef
        p=self.observation();p['request_id']=uuid.uuid4().hex
        action=action_to_eef(args,p);targets=action['target'];start=self.env.tick
        for _ in range(action['steps']):
            proposal=self.env.call('eef_joint_target',targets=targets);row=proposal['action']
            self.env.step({f'{a}_{f}':row[o:o+n] for a,b in (('left',0),('right',7)) for f,o,n in (('arm_joint_state',b,6),('ee_joint_state',b+6,1))})
            if self.env.ended:break
        result=self.observation()
        append_trace(self.args.output,dict(event='custom_delta_action',arguments=args,start_step=start,end_step=self.env.tick,measured_eef_after=result['current_eef']))
        return result
    def batch_result(self):
        outcome=read(self.args.output.parent/'sim/evaluation_outcome.json')
        return dict(status='succeeded',successes=int(bool(outcome.get('native_success'))),total_episodes=1,completed_episodes=1,
            success_rate=float(bool(outcome.get('native_success'))),result_path=str(self.args.output.parent/'sim/evaluation_outcome.json'),episodes=[outcome])
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
