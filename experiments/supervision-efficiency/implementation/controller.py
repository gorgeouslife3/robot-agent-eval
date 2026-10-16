"""Astra Hybrid with a common fixed VLA refresh and configurable reviews."""
import argparse
import base64
from collections import deque
import io
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
import uuid

import numpy as np
from PIL import Image
from support import ROOT, OWNED, Ledger, append, read, write, owned, sha
from monitor import Monitor, review_due

sys.path.insert(0, str(ROOT/'source-snapshots/astra_policy'))
from hybrid_rollout.robodojo.robodojo_server.protocol import RPCClient
from hybrid_rollout.robodojo.pi05_server.client import Pi05Client
from hybrid_rollout.robodojo.robodojo_server.client import validate_dual_response
from hybrid_rollout.robodojo.robodojo_server.gate_assessment import validate_assessment
from hybrid_rollout.robodojo.robodojo_server.action_edit_kinematics import edited_targets
from hybrid_rollout.robodojo.robodojo_server.validation import angles


def obj(properties, nullable=False):
    return dict(type=['object','null'] if nullable else 'object', properties=properties,
                required=list(properties), additionalProperties=False)


def vector(n):
    return dict(type='array',items=dict(type='number'),minItems=n,maxItems=n)


def decision_tool():
    text=dict(type='string')
    progress=obj(dict(verified_completed=dict(type='array',items=text),
                      currently_attempting=text,remaining=dict(type='array',items=text)))
    assessment=obj(dict(task_progress=progress,current_subgoal=text,
        execution_status=dict(type='string',enum=['not_started','progressing','failed','uncertain','recovered']),
        execution_evidence=text,expected_next_intent=text,predicted_next_intent=text,
        intent_status=dict(type='string',enum=['aligned','misaligned','uncertain']),intent_evidence=text))
    pose=obj(dict(position=vector(3),quaternion_wxyz=vector(4),gripper_closed=dict(type='boolean')))
    edit=obj(dict(delta_position=vector(3),delta_rotation_vector=vector(3),
                  gripper=dict(type='string',enum=['keep','open','closed'])))
    parameters=obj(dict(mode=dict(type='string',enum=['student','eef','edit']),
        correction_steps=dict(type='integer',minimum=1,maximum=5),reason=text,
        assessment=assessment,target=obj(dict(left=pose,right=pose),True),
        edit=obj(dict(left=edit,right=edit),True),
        memory=obj(dict(arm=dict(type='string',enum=['left','right']),
            grasp_verified=dict(type='boolean'),facts=dict(type='array',items=text,maxItems=6)))))
    return dict(type='function',name='supervise',description='Review current evidence and pending VLA actions; authorize or make a bounded correction.',
                parameters=parameters,strict=True)


def image_part(path):
    rgb=Image.open(path).convert('RGB')
    rgb.thumbnail((480,480))
    stream=io.BytesIO();rgb.save(stream,format='JPEG',quality=90)
    return dict(type='input_image',image_url='data:image/jpeg;base64,'+
        base64.b64encode(stream.getvalue()).decode(),detail='high')


def payload(request, previous, memory, recent, summary, error, config):
    # Group ID and scheduling policy are deliberately absent from model input.
    content=[dict(type='input_text',text=json.dumps(dict(
        observation={k:v for k,v in request.items() if k!='images'},monitor=summary,
        bounded_memory=memory,recent_executions=list(recent),last_validation_error=error),allow_nan=False))]
    for image in request['images']:
        content.extend([dict(type='input_text',text='Current '+image['camera']),image_part(image['path'])])
    if previous is not None:
        image=next(x for x in previous['images'] if x['camera']=='cam_high')
        content.extend([dict(type='input_text',text='Head view at previous review, step '+str(previous['step_id'])),image_part(image['path'])])
    return dict(model=config['model'],reasoning=dict(effort=config['reasoning_effort']),
        instructions=(OWNED/'configs/hybrid-prompt.md').read_text(),input=[dict(role='user',content=content)],
        tools=[decision_tool()],tool_choice=dict(type='function',name='supervise'),parallel_tool_calls=False,
        max_output_tokens=config['max_output_tokens_per_request'],store=False,stream=False)


class Model:
    def __init__(self,config,directory):
        self.config=config;self.directory=directory;self.calls=0;self.input_tokens=0
        self.url=os.environ['ROBOT_SUPERVISION_PROXY_URL'].rstrip('/')+'/responses'
        if not self.url.startswith('http://127.0.0.1:'):
            raise ValueError('Owned loopback model proxy required')

    def request(self,value,remaining_s):
        if self.calls>=self.config['max_model_calls_per_episode']:
            raise RuntimeError('model_call_budget')
        if self.input_tokens>=self.config['max_input_tokens_per_episode']:
            raise RuntimeError('input_token_budget')
        index=self.calls;self.calls+=1
        write(self.directory/f'model_input_{index:03d}.json',value)
        request=urllib.request.Request(self.url,data=json.dumps(value,allow_nan=False).encode(),
            headers={'Content-Type':'application/json','Authorization':'Bearer owned-loopback'})
        try:
            with urllib.request.urlopen(request,timeout=min(self.config['request_timeout_s']+5,max(1.,remaining_s))) as reply:
                result=json.load(reply)
        except Exception as error:
            write(self.directory/f'model_error_{index:03d}.json',dict(error_type=type(error).__name__))
            raise RuntimeError('model_transport_error:'+type(error).__name__) from None
        write(self.directory/f'model_output_{index:03d}.json',dict(
            model=result.get('model'),status=result.get('status'),usage=result.get('usage'),
            response_id=result.get('id'),output=[x for x in result.get('output',[]) if x.get('type') in ('message','function_call')]))
        if result.get('model')!=self.config['model'] or result.get('status')!='completed':
            raise RuntimeError('model_identity_or_status_error')
        usage=result.get('usage')
        if not isinstance(usage,dict) or not isinstance(usage.get('input_tokens'),int):
            raise RuntimeError('model_usage_missing')
        self.input_tokens+=usage['input_tokens']
        if self.input_tokens>self.config['max_input_tokens_per_episode']:
            raise RuntimeError('input_token_budget')
        calls=[x for x in result.get('output',[]) if x.get('type')=='function_call' and x.get('name')=='supervise']
        if len(calls)!=1:
            raise ValueError('Exactly one supervise call required')
        return json.loads(calls[0]['arguments'])


def adapt_decision(args, request, prefix_length):
    memory=args['memory']
    if memory['arm'] not in ('left','right') or type(memory['grasp_verified']) is not bool:
        raise ValueError('Invalid memory arm or grasp status')
    if len(memory['facts'])>6 or any(not isinstance(f,str) or len(f)>180 for f in memory['facts']):
        raise ValueError('Memory permits six facts of at most 180 characters each')
    mode=args['mode']
    n=prefix_length if mode=='student' else args['correction_steps']
    response=dict(request_id=request['request_id'],mode=mode,steps=n,
                  reason=args['reason'],assessment=args['assessment'])
    if mode=='eef':response['target']=args['target']
    if mode=='edit':response['edit']=args['edit']
    validate_dual_response(response,request)
    validate_assessment(response,request)
    return response,memory


def corrections(response, trajectory):
    if response['mode']=='eef':return [response['target']]*response['steps']
    arms={}
    for arm in ('left','right'):
        original=[p[arm] for p in trajectory]
        arms[arm]=edited_targets(original,response['steps'],response['edit'][arm])
        if response['edit'][arm]['gripper']=='keep':
            for target,initial in zip(arms[arm],original):
                target['gripper_opening']=initial['gripper_opening']
    return [{arm:arms[arm][i] for arm in arms} for i in range(response['steps'])]


def run(args):
    directory=owned(args.output);directory.mkdir(parents=True,exist_ok=False)
    config=read(args.config);group=config['groups'][args.group]
    monitor=Monitor(config['monitor']);ledger=Ledger(directory/'time_events.jsonl')
    model=Model(config,directory)
    policy=Pi05Client(args.policy_port,args.checkpoint)
    sim=RPCClient('127.0.0.1',args.sim_port,timeout=600)
    episode=None;tick=0;last_review=0;review_count=0;active_start=None;active_end=None
    stopped='controller_error';done=False;actions=None;offset=0;prediction=None;fk=None
    memory=dict(arm='right',grasp_verified=False,facts=[])
    recent=deque(maxlen=3);previous=None;counts=dict(student_steps=0,edit_steps=0,eef_steps=0,
        vla_inferences=0,phase_triggers=0,anomaly_triggers=0,shadow_phase_events=0,shadow_anomaly_events=0,
        actual_review_triggers=0,rejected_actions=0,recovery_attempts=0,recovery_successes=None)
    try:
        reset=sim.request('reset',seed=args.layout,source='student',policy_version='supervision_part2')
        episode=reset['episode_id'];active_start=time.perf_counter()
        write(directory.parent/'active_clock.json',dict(start_monotonic=active_start))
        if 'shovel' not in reset['instruction'].lower():
            raise RuntimeError('Native instruction is not the authorized shovel task')
        if reset['metadata']['max_episode_steps']!=200:
            raise RuntimeError('Unexpected native control budget')
        write(directory/'reset_public.json',reset)
        while not done:
            remaining=config['max_episode_wall_s']-(time.perf_counter()-active_start)
            if remaining<=0:raise RuntimeError('wall_budget')
            with ledger.measure('logging_ipc'):
                observation=sim.request('teacher_observation',episode_id=episode,step_id=tick)
                frames=directory/'observations'/f'{tick:04d}'
                frames.mkdir(parents=True,exist_ok=True)
                images=[]
                for camera in ('cam_high','cam_left_wrist','cam_right_wrist'):
                    path=frames/(camera+'.png');Image.fromarray(observation[camera]).save(path)
                    images.append(dict(camera=camera,path=str(path)))
            if actions is None or offset>=15:
                with ledger.measure('vla_infer',step_id=tick):
                    location=directory/'proposals'/f'{counts["vla_inferences"]:03d}'
                    location.mkdir(parents=True)
                    actions,prediction=policy.infer(observation,location/'actions.npz')
                    prediction['generation_step']=tick
                    fk=sim.request('fk_preview',episode_id=episode,step_id=tick,actions=actions)
                offset=0;counts['vla_inferences']+=1
                write(location/'identity.json',dict(prediction,step_id=tick,fk_check=fk['measured_fk_check']))
            available=min(15-offset,int(observation['remaining_steps']))
            with ledger.measure('monitor',step_id=tick):
                summary=monitor.update(observation,tick,actions[offset:offset+min(5,available)])
            counts['shadow_phase_events']+=len(summary['phase_events'])
            counts['shadow_anomaly_events']+=len(summary['anomaly_events'])
            reasons=review_due(group,tick,last_review,summary,initial=review_count==0)
            request=dict(request_id=uuid.uuid4().hex,episode_id=episode,step_id=tick,
                gate_policy='failure-or-intent',instruction=observation['instruction'],
                remaining_steps=int(observation['remaining_steps']),remaining_wall_s=max(0.,remaining),
                current_state=observation['states'].tolist(),
                current_eef={arm:angles(dict(position=observation['eef_positions'][i].tolist(),
                    quaternion_wxyz=observation['eef_quaternions_wxyz'][i].tolist(),
                    gripper_opening_command=float(observation['states'][i*7+6])))
                    for i,arm in enumerate(('left','right'))},images=images,
                student_eef_trajectory=fk['trajectory'][offset:],
                pending_prefix_steps=available,proposal_generation_step=prediction.get('generation_step'),
                proposal_inference_index=prediction['inference_index'],proposal_offset=offset,
                fk_scope='Robot-only targets, not contact, object motion or future success')
            response=None
            append(directory/'monitor_trace.jsonl',dict(summary,reasons=reasons,review_due=bool(reasons),
                group_id=args.group,observation_version=f'{episode}:{tick}',proposal_inference_index=prediction['inference_index']))
            if reasons:
                last_review=tick;counts['actual_review_triggers']+=1
                counts['phase_triggers']+=int(any(r.startswith('phase:') for r in reasons))
                counts['anomaly_triggers']+=int(any(r.startswith('anomaly:') for r in reasons))
                validation_error=None
                for retry in range(3):
                    try:
                        with ledger.measure('logging_ipc'):
                            value=payload(request,previous,memory,recent,summary,validation_error,config)
                        with ledger.measure('astra_blocked',step_id=tick):
                            raw=model.request(value,config['max_episode_wall_s']-(time.perf_counter()-active_start))
                        response,next_memory=adapt_decision(raw,request,available)
                        break
                    except (ValueError,KeyError,TypeError) as error:
                        validation_error=str(error);counts['rejected_actions']+=1
                        append(directory/'rejections.jsonl',dict(step_id=tick,error=validation_error))
                if response is None:raise RuntimeError('three_invalid_model_decisions')
                if time.perf_counter()-active_start>=config['max_episode_wall_s']:
                    raise RuntimeError('wall_budget')
                with ledger.measure('logging_ipc'):
                    sim.request('record_codex_decision',episode_id=episode,step_id=tick,
                        decision=review_count,prediction_id=prediction['prediction_id'],response=response)
                    append(directory/'reviews.jsonl',dict(step_id=tick,review_index=review_count,
                        reasons=reasons,response=response,memory=next_memory,previous_review_step=previous['step_id'] if previous else None))
                review_count+=1;memory=next_memory;monitor.choose_arm(memory['arm'])
                previous=request
            start=tick;trace=[]
            if response is not None and response['mode']!='student':
                counts['recovery_attempts']+=1;monitor.recovery_pending=True
                with ledger.measure('action_ack',step_id=tick,source=response['mode']):
                    sim.request('switch_control_source',episode_id=episode,step_id=tick,
                                source='gpt_eef',reason=response['reason'])
                    for target in corrections(response,request['student_eef_trajectory']):
                        proposal=sim.request('eef_joint_target',episode_id=episode,step_id=tick,targets=target)
                        result=sim.request('chunk_step',episode_id=episode,step_id=tick,
                            actions=np.asarray([proposal['action']],np.float32),teacher_request_id=request['request_id'])
                        tick=result['step_id'];trace.extend(result['steps'])
                        if any(r['terminated'] or r['truncated'] for r in result['steps']):break
                source=response['mode'];actions=None
            else:
                source='student';n=min(5,available)
                with ledger.measure('action_ack',step_id=tick,source=source):
                    sim.request('switch_control_source',episode_id=episode,step_id=tick,source='student',
                                reason='Continue authorized VLA within the common 15-step refresh')
                    result=sim.request('chunk_step',episode_id=episode,step_id=tick,
                        actions=actions[offset:offset+n],student_prediction_id=prediction['prediction_id'])
                tick=result['step_id'];trace=result['steps'];offset+=tick-start
            counts[source+'_steps']+=tick-start
            done=bool(trace and (trace[-1]['terminated'] or trace[-1]['truncated']))
            execution=dict(start_step=start,end_step=tick,source=source,
                proposal_inference_index=prediction['inference_index'],proposal_offset=offset,
                measured_eef_before=request['current_eef'],executed_gripper_commands=[
                    [float(r['executed_action'][6]),float(r['executed_action'][13])] for r in trace],
                reason=response['reason'] if response else 'Continue current VLA authorization')
            recent.append(execution)
            append(directory/'execution_trace.jsonl',execution)
            write(directory/'progress.json',dict(step_id=tick,review_count=review_count,api_submitted=model.calls,**counts))
            print(json.dumps(dict(group=args.group,step=tick,reviews=review_count,source=source)),flush=True)
        stopped='native_terminal';active_end=time.perf_counter()
    except Exception as error:
        active_end=time.perf_counter()
        stopped=str(error) if str(error) in ('wall_budget','model_call_budget','input_token_budget') or str(error).startswith('model_transport_error') else 'controller_error'
        write(directory/'failure.json',dict(error_type=type(error).__name__,error=str(error)))
    finally:
        if episode is not None:
            try:
                sim.request('finish_pilot',episode_id=episode,step_id=tick,reason=stopped)
            except Exception as error:
                write(directory/'finish_error.json',dict(error_type=type(error).__name__))
        sim.close();policy.close()
        elapsed=active_end-active_start if active_start is not None and active_end is not None else None
        write(directory/'summary.json',dict(group_id=args.group,step_id=tick,stop_reason=stopped,
            review_count=review_count,api_submitted=model.calls,activity_start_monotonic=active_start,
            activity_end_monotonic=active_end,episode_active_wall_s=elapsed,time_categories=ledger.sums,
            timing_residual_s=elapsed-sum(ledger.sums.values()) if elapsed is not None else None,
            input_tokens_recorded=model.input_tokens,**counts))
    return stopped


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--sim-port',type=int,required=True)
    parser.add_argument('--policy-port',type=int,required=True)
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--group',required=True)
    parser.add_argument('--layout',type=int,required=True)
    raise SystemExit(0 if run(parser.parse_args())=='native_terminal' else 1)
