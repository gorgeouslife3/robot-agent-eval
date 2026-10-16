"""Action/feedback, resource and isolation checks without GPU or paid requests."""
from copy import deepcopy
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from robot_agent_eval.common import ROOT, source_path, write
from robot_agent_eval.react_harness import (action_to_eef, build_payload, load_bundle,
    parse_action, preview, run_loop, ResponsesClient, BudgetReached)
from robot_agent_eval.runner import make_result
from robot_agent_eval.aggregate import summarize


def packet():
    return dict(task='general_pickup', instruction='Pick up the lavender plastic shovel by 10 cm.',
        step_id=0, remaining_steps=200, current_state=[0.]*14,
        request_id='observation-0', rollout_finished=False, images=[],
        current_eef={arm:dict(position=[sign*.3, -.35, .92], quaternion_wxyz=[1.,0.,0.,0.],
                             gripper_opening_command=1.) for arm,sign in [('left',-1),('right',1)]})


def action():
    return dict(stage='approach', evidence='The handle is ahead of the right hand.',
        expected_effect='Reach above the handle.', next_check='Check lateral alignment.',
        memory={'grasp_verified':False,'facts':['Right hand selected.']}, arm='right',
        translation_m=[0.,.04,0.], rotation_xyz_deg=[0.,0.,10.], gripper='keep',control_steps=5)


class ReactHarness(unittest.TestCase):
    def test_relative_motion_holds_other_arm_and_uses_measured_pose(self):
        p=packet();a=action();out=action_to_eef(a,p)
        self.assertEqual(out['request_id'],p['request_id'])
        self.assertEqual(out['target']['left']['position'],p['current_eef']['left']['position'])
        self.assertEqual(out['target']['left']['quaternion_wxyz'],[1.,0.,0.,0.])
        self.assertAlmostEqual(out['target']['right']['position'][1],-.31)
        self.assertAlmostEqual(out['target']['right']['quaternion_wxyz'][0],math.cos(math.radians(5)))
        self.assertEqual(p,packet())

    def test_rotation_matches_upstream_xyz_world_convention(self):
        from scipy.spatial.transform import Rotation
        p=packet();q=Rotation.from_euler('xyz',[20,35,40],degrees=True).as_quat()
        p['current_eef']['right']['quaternion_wxyz']=q[[3,0,1,2]].tolist()
        a=action();a['rotation_xyz_deg']=[5.,-3.,7.]
        got=action_to_eef(a,p)['target']['right']['quaternion_wxyz']
        expected=Rotation.from_euler('xyz',a['rotation_xyz_deg'],degrees=True)*Rotation.from_quat(q)
        difference=Rotation.from_quat([got[1],got[2],got[3],got[0]])*expected.inv()
        self.assertLess(difference.magnitude(),1e-10)

    def test_unsafe_or_malformed_actions_are_rejected_before_mutation(self):
        bad=[]
        for changes in [dict(translation_m=[.04,.04,0]),dict(rotation_xyz_deg=[18,18,0]),
                        dict(translation_m=[float('nan'),0,0]),dict(control_steps=True),
                        dict(gripper='reset'),dict(control_steps=6),dict(arm='support_arm'),
                        dict(memory={'grasp_verified':'yes','facts':[]})]:
            a=action();a.update(changes);bad.append(a)
        for a in bad:
            p=packet()
            with self.subTest(action=a),self.assertRaises(ValueError):action_to_eef(a,p)
            self.assertEqual(p,packet())

    def test_native_remaining_steps_bound_and_gripper_hold(self):
        p=packet();p['remaining_steps']=2
        with self.assertRaises(ValueError):action_to_eef(action(),p)
        p=packet();p['current_eef']['left']['gripper_opening_command']=0.
        a=action();a['gripper']='close'
        out=action_to_eef(a,p)
        self.assertTrue(out['target']['left']['gripper_closed'])
        self.assertTrue(out['target']['right']['gripper_closed'])

    def test_task_and_instruction_routing_does_not_apply_shovel_skill_to_brush(self):
        for task,text in [('align_blocks','Use the set square'),('general_pickup','Pick up the blue brush')]:
            with self.assertRaises(ValueError):load_bundle(task,text)
        full=load_bundle('general_pickup',packet()['instruction'])
        generic=load_bundle('general_pickup',packet()['instruction'],use_skill=False)
        self.assertNotEqual(full['prompt_sha256'],generic['prompt_sha256'])
        self.assertIsNone(generic['skill_id'])

    def test_model_cannot_claim_success_or_call_another_tool(self):
        r=dict(model='gpt-6-astra',status='completed',output=[dict(type='function_call',
             name='finish',arguments='{}')])
        with self.assertRaises(ValueError):parse_action(r,'gpt-6-astra')
        r['output'][0]['name']='robot_action';r['output'][0]['arguments']=json.dumps(action())
        self.assertEqual(parse_action(r,'gpt-6-astra'),action())
        r['model']='another-model'
        with self.assertRaises(ValueError):parse_action(r,'gpt-6-astra')

    def test_payload_whitelist_excludes_privileged_and_accounting_fields(self):
        p=packet();p.update(layout_path='/secret/layout.json',native_score=100,
                           object_positions=[1,2,3],history_path='/unbounded/history.json')
        config=read_config()
        payload=build_payload(p,load_bundle(p['task'],p['instruction']),config)
        text=payload['input'][0]['content'][0]['text']
        for forbidden in ('/secret','native_score','object_positions','history_path'):
            self.assertNotIn(forbidden,text)
        self.assertFalse(payload['parallel_tool_calls']);self.assertFalse(payload['store'])

    def test_preview_uses_recorded_images_without_credentials_or_network(self):
        with tempfile.TemporaryDirectory() as temp,patch('urllib.request.urlopen',side_effect=AssertionError('Network used')):
            from PIL import Image
            fixture=packet()
            for camera in ('cam_head', 'cam_left_wrist', 'cam_right_wrist'):
                path=Path(temp)/(camera+'.png')
                Image.new('RGB', (32,32), (100,120,140)).save(path)
                fixture['images'].append(dict(camera=camera,path=str(path)))
            obs=Path(temp)/'observation.json';write(obs,fixture)
            p=preview(obs,ROOT/'configs/model.react-pilot.json',Path(temp)/'preview')
            body=json.loads((p/'model_input.json').read_text())
            self.assertEqual(sum(c['type']=='input_image' for c in body['input'][0]['content']),3)
            self.assertNotIn('api_key_file',body)

    def test_feedback_loop_stops_on_native_terminal_and_rejections_do_not_execute(self):
        source_path()
        class FakeTools:
            task='general_pickup'
            def __init__(self):self.history=[];self.p=packet();self.executions=0
            def next_call(self):return dict(tool='robodojo_start' if not self.history else 'robodojo_act',
                                           observation_path='observation.json',output_dir='unused')
            def start(self,**kwargs):return deepcopy(self.p)
            def act(self,**kwargs):
                self.executions+=1;self.history.append(kwargs['response'])
                self.p['step_id']+=5;self.p['remaining_steps']-=5
                self.p['current_eef']['right']['position'][1]+=.03
                self.p['request_id']=f'observation-{self.executions}'
                self.p.update(rollout_finished=self.executions==2,result={'native_success':True})
                return deepcopy(self.p)
        class FakeModel:
            def __init__(self):self.inputs=[]
            def request(self,payload):
                self.inputs.append(payload);a=action()
                if len(self.inputs)==1:a['translation_m']=[.1,0,0]
                return dict(status='completed',model='gpt-6-astra',output=[dict(type='function_call',
                            name='robot_action',arguments=json.dumps(a))])
        tools,model=FakeTools(),FakeModel()
        with tempfile.TemporaryDirectory() as temp:
            # Fake observations have no cameras; the real build_payload is exercised elsewhere.
            with patch('robot_agent_eval.react_harness.image_content',return_value={}),patch(
                    'robot_agent_eval.react_harness.build_payload',side_effect=lambda p,b,c,**kw:
                    dict(model=c['model'],input=json.dumps(dict(step=p['step_id'],**kw),default=list))):
                result=run_loop(tools,model,read_config(),temp,load_bundle(tools.task))
            trace=[json.loads(l) for l in (Path(temp)/'react_trace.jsonl').read_text().splitlines()]
            self.assertEqual([e['event'] for e in trace],['rejected','executed','executed'])
            self.assertEqual(tools.executions,2);self.assertEqual(len(model.inputs),3)
            self.assertTrue(result['native_success'])
            self.assertEqual(json.loads(model.inputs[-1]['input'])['step'],5)
            self.assertEqual(json.loads(model.inputs[1]['input'])['memory'],{'grasp_verified':False,'facts':[]})

    def test_model_call_budget_checked_before_network(self):
        config=read_config()
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'ROBOT_REACT_PROXY_URL':'http://127.0.0.1:1/v1'}):
            client=ResponsesClient(config,temp);client.calls=config['max_model_calls_per_episode']
            with patch('urllib.request.urlopen',side_effect=AssertionError('Network used')),self.assertRaises(BudgetReached):
                client.request({})

    def test_usage_is_persisted_without_private_reasoning_even_on_token_abort(self):
        config=read_config();config['max_total_tokens_per_episode']=10
        response=dict(model=config['model'],status='completed',id='fake-response',
                      usage={'input_tokens':8,'output_tokens':4,'total_tokens':12},
                      output=[{'type':'reasoning','private_test_marker':'must-not-be-saved'},
                              {'type':'function_call','name':'robot_action','arguments':json.dumps(action())}])
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'ROBOT_REACT_PROXY_URL':'http://127.0.0.1:1/v1'}):
            client=ResponsesClient(config,temp)
            with patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(response).encode())),self.assertRaises(BudgetReached):
                client.request({'model':config['model']})
            saved=(Path(temp)/'model_output_000.json').read_text()
            self.assertNotIn('must-not-be-saved',saved)
            self.assertEqual(json.loads(saved)['usage']['total_tokens'],12)
            self.assertEqual(client.total_tokens,12)

    def test_react_accounting_is_not_marked_as_no_model_and_skill_versions_do_not_merge(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            write(p/'launch.json',dict(method='astra_react_skill',split='test',case={'case_id':'one'},calibration=False,
                                      harness={'prompt_sha256':'v1','skill_id':'shovel'}))
            write(p/'process_result.json',dict(status='wall_budget'))
            write(p/'sim/reset.json',{})
            (p/'model_request_starts.jsonl').write_text('{"call":1}\n')
            row=make_result(p)
            self.assertFalse(row['model_usage_complete']);self.assertEqual(row['model_requests'],1)
            self.assertNotIn('not applicable',row['model_request_accounting'])
            other=dict(row,harness_prompt_sha256='v2')
            self.assertEqual(len(summarize([row,other])),2)


def read_config():
    return json.loads((ROOT/'configs/model.react-pilot.json').read_text())


if __name__=='__main__':unittest.main()
