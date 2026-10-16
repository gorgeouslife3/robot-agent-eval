"""Provider and sensor adapters, retaining framework-owned planning/tool loops."""
import base64
import io
import json
import os
from pathlib import Path
import time
import threading
import numpy as np
from PIL import Image
from .common import ROOT, source_path, write
from .react_harness import ResponsesClient


def image_block(data):
    if isinstance(data, np.ndarray):
        b=io.BytesIO();Image.fromarray(data[...,:3].astype(np.uint8)).save(b,format='PNG');data=b.getvalue()
    return {'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(data).decode()}}


def responses_payload(messages, config, tools=None):
    """Lossless public chat history to Responses, without model substitutions."""
    instructions=[];items=[]
    for m in messages:
        role=m['role'];content=m.get('content')
        if role=='system':
            instructions.append(content if isinstance(content,str) else json.dumps(content));continue
        if role=='tool':
            items.append(dict(type='function_call_output',call_id=m['tool_call_id'],output=content or ''));continue
        if content:
            if isinstance(content,str):content=[dict(type='input_text' if role!='assistant' else 'output_text',text=content)]
            else:
                converted=[]
                for b in content:
                    if b['type'] in ('text','input_text','output_text'):
                        converted.append(dict(type='output_text' if role=='assistant' else 'input_text',text=b['text']))
                    elif b['type']=='image_url':
                        u=b['image_url'];converted.append(dict(type='input_image',image_url=u['url'] if isinstance(u,dict) else u,detail='high'))
                    elif b['type']=='image':
                        s=b['source'];converted.append(dict(type='input_image',image_url='data:'+s['media_type']+';base64,'+s['data'],detail='high'))
                    else:raise ValueError('Unsupported public content block '+b['type'])
                content=converted
            items.append(dict(role=role,content=content))
        for tc in m.get('tool_calls',[]):
            items.append(dict(type='function_call',call_id=tc['id'],name=tc['function']['name'],arguments=tc['function']['arguments']))
    payload=dict(model=config['model'],instructions='\n\n'.join(instructions),input=items,
        reasoning={'effort':config['reasoning_effort']},store=False,stream=False,parallel_tool_calls=False,
        max_output_tokens=config.get('max_output_tokens_per_request',16384))
    if tools:
        payload['tools']=[dict(type='function',name=t.get('function',t)['name'],description=t.get('function',t).get('description',''),
            parameters=t.get('function',t).get('parameters',t.get('function',t).get('input_schema',{})),strict=False) for t in tools]
    return payload


def chat_reply(response):
    if response.get('status')!='completed':raise RuntimeError('Incomplete Astra response: '+str(response.get('status')))
    text=[];calls=[]
    for o in response.get('output',[]):
        if o.get('type')=='message':text.extend(b['text'] for b in o.get('content',[]) if b['type']=='output_text')
        elif o.get('type')=='function_call':calls.append(dict(id=o['call_id'],type='function',function={'name':o['name'],'arguments':o['arguments']}))
    m=dict(role='assistant',content='\n'.join(text) or None)
    if calls:m['tool_calls']=calls
    return dict(choices=[dict(message=m,finish_reason='tool_calls' if calls else 'stop')],usage=response['usage'])


class PublicEnv:
    """One native RPC owner; only public sensors/proprioception and robot IK."""
    def __init__(self, port, layout, output, method):
        source_path()
        from hybrid_rollout.robodojo.robodojo_server.protocol import RPCClient
        self.rpc=RPCClient('127.0.0.1',port);self.output=Path(output);self.method=method
        self.rpc_lock=threading.RLock()
        self.reset=self.rpc.request('reset',seed=layout,source='gpt_joint',policy_version=method)
        self.episode=self.reset['episode_id'];self.tick=self.reset['step_id'];self.ended=False
        self.eval_fair=True;self.control_wall=0.;self.observation=self.get_obs()
        self.save_observation('initial')
        required=method in ('rpent_astra','gap_astra','modular_pickup','modular_calibration','graspnet_calibration')
        contract={n:dict(rgb_shape=list(np.asarray(c['color']).shape),
            depth_shape=list(np.asarray(c.get('depth')).shape) if c.get('depth') is not None else None,
            intrinsic_shape=list(np.asarray(c.get('intrinsic_matrix')).shape),
            extrinsic_shape=list(np.asarray(c.get('extrinsic_matrix')).shape)) for n,c in self.observation['vision'].items()}
        valid=bool(contract) and all(c['depth_shape']==c['rgb_shape'][:2] and c['intrinsic_shape']==[3,3]
            and c['extrinsic_shape']==[4,4] for c in contract.values())
        write(self.output/'sensor_contract.json',dict(required_rgbd=required,valid_rgbd=valid,cameras=contract))
        if required and not valid:
            self.rpc.close()
            raise ValueError('Native RGB-D/calibration sensor contract incomplete; framework trial not admitted')
    def call(self,op,**kwargs):
        with self.rpc_lock:
            try:return self.rpc.request(op,episode_id=self.episode,step_id=self.tick,**kwargs)
            except Exception as error:
                append_trace(self.output,dict(event='native_rpc_error',op=op,step=self.tick,error_type=type(error).__name__,error=str(error)))
                raise
    def get_obs(self):
        with self.rpc_lock:
            obs=self.call('public_observation');self.observation=obs;return obs
    def save_observation(self,name):
        d=self.output/'sensors'/name;d.mkdir(parents=True,exist_ok=True)
        obs=self.observation
        state={k:np.asarray(v).tolist() for k,v in obs['state'].items()}
        write(d/'state.json',dict(instruction=obs['instruction'],state=state,step=obs['step'],step_limit=obs['step_limit']))
        arrays={}
        for n,c in obs['vision'].items():
            Image.fromarray(np.asarray(c['color'],np.uint8)[...,:3]).save(d/(n+'.png'))
            for key in ('depth','distance_to_image_plane','intrinsic_matrix','extrinsic_matrix'):
                if c.get(key) is not None:arrays[n+'_'+key]=np.asarray(c[key])
        np.savez_compressed(d/'public_rgbd.npz',**arrays)
    def solve_ik_position(self,arm,xyz):return self.call('public_position_ik',arm=arm,xyz=xyz)
    def get_task_language(self):return self.observation['instruction']
    def get_status(self):return dict(step=self.tick,step_limit=self.observation['step_limit'],done=self.ended)
    def solve_pose(self,arm,pose):return self.call('public_pose_ik',arm=arm,pose=pose)
    def step(self,action):
        with self.rpc_lock:return self._step(action)
    def _step(self,action):
        if self.ended:raise RuntimeError('Native episode already ended')
        before=time.perf_counter();r=self.call('public_native_step',command=action);self.control_wall+=time.perf_counter()-before
        if r.get('error'):raise RuntimeError(r['error'])
        self.tick=r['step_id'];rows=r['steps'];self.ended=any(x['terminated'] or x['truncated'] for x in rows)
        obs=self.get_obs();self.save_observation(f'{self.tick:04d}')
        return obs,0.,self.ended,dict(status={'step':self.tick,'step_limit':obs['step_limit']})
    def is_success(self):raise RuntimeError('Official evaluation is not an agent planning tool')
    def close(self):
        with self.rpc_lock:self._close()
    def _close(self):
        if self.rpc.sock is None:return
        try:self.call('finish_pilot',reason='framework_returned' if not self.ended else 'terminal')
        except Exception as error:
            # Cleanup errors must not replace the original controller failure.
            write(self.output/'cleanup_error.json',dict(error_type=type(error).__name__,error=str(error)))
        finally:self.rpc.close()


def public_state_content(obs):
    state={k:np.asarray(v).tolist() for k,v in obs['state'].items()}
    content=[dict(type='text',text=json.dumps(dict(instruction=obs['instruction'],state=state,step=obs['step'],step_limit=obs['step_limit'])))]
    for n,c in obs['vision'].items():
        content.extend([dict(type='text',text=n),image_block(np.asarray(c['color']))])
    return content


def append_trace(output,entry):
    with (Path(output)/'framework_trace.jsonl').open('a') as f:f.write(json.dumps(entry,ensure_ascii=False,default=str)+'\n')


class RPentPolicy:
    """Map the public dictionary contract to the pinned OpenPI checkpoint."""
    def __init__(self,args):
        from hybrid_rollout.robodojo.pi05_server.client import Pi05Client
        self.client=Pi05Client(args.policy_port,args.checkpoint);self.output=args.output;self.count=0
    def predict(self,obs):
        state=np.concatenate([np.r_[obs['state'][f'{a}_arm_joint_state'],obs['state'][f'{a}_ee_joint_state']] for a in ('left','right')])
        native=dict(states=state,instruction=obs['instruction'],**{('cam_high' if n=='cam_head' else n):np.asarray(c['color'])[...,:3] for n,c in obs['vision'].items()})
        actions,meta=self.client.infer(native,self.output/f'policy_proposal_{self.count:03d}.npz');self.count+=1
        write(self.output/f'policy_proposal_{self.count-1:03d}.json',meta)
        # The pinned checkpoint's order is left6,leftgrip,right6,rightgrip.
        return [{f'{a}_{field}':row[offset:offset+n].tolist() for a,base in (('left',0),('right',7))
            for field,offset,n in (('arm_joint_state',base,6),('ee_joint_state',base+6,1))} for row in actions]
    def close(self):self.client.close()
