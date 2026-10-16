"""Offline scheduler, action gate, tracker and fixed-refresh integration checks."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image

from support import ROOT, OWNED, read
from monitor import Monitor,review_due
import controller


MONITOR=dict(hsv_low=[115,12,90],hsv_high=[155,95,255],minimum_component_pixels=100,
    maximum_centroid_jump_pixels=90,trial_lift_m=.015,failed_lift_m=.02,
    co_motion_pixels=3.,stationary_pixels=2.5,stationary_hand_m=.005)


def observation(step=0,closed=False,rise=0.,pixel_shift=0,visible=True):
    image=np.zeros((480,640,3),np.uint8)
    if visible:image[180:230,300+pixel_shift:330+pixel_shift]=[205,193,219]
    state=np.zeros(14,np.float32);state[[6,13]]=0. if closed else 1.
    return dict(cam_high=image,cam_left_wrist=image,cam_right_wrist=image,
        states=state,eef_positions=np.array([[0,0,.9],[0,0,.9+rise]],np.float32),
        eef_quaternions_wxyz=np.array([[1,0,0,0],[1,0,0,0]],np.float32),
        instruction='Pick up the lavender plastic shovel by 10 cm',remaining_steps=200-step)


def fake_decision(request):
    first=request['step_id']==0
    return dict(mode='student',correction_steps=1,reason='The next proposal continues the visible shovel task.',
        assessment=dict(task_progress=dict(verified_completed=[],currently_attempting='approach',remaining=['grasp','lift']),
            current_subgoal='approach',execution_status='not_started' if first else 'progressing',
            execution_evidence='No execution yet' if first else 'Measured hand state remains valid',
            expected_next_intent='approach shovel',predicted_next_intent='approach shovel',
            intent_status='aligned',intent_evidence='Robot-only FK and gripper sequence'),
        target=None,edit=None,memory=dict(arm='right',grasp_verified=False,facts=[]))


class FakeSim:
    def __init__(self,*args,**kwargs):self.tick=0;self.closed=False;self.alive=True
    def request(self,op,**kw):
        if op=='reset':return dict(episode_id='offline',step_id=0,instruction='Pick up the lavender plastic shovel by 10 cm',metadata=dict(max_episode_steps=200))
        if op=='teacher_observation':return observation(self.tick,self.closed)
        if op=='fk_preview':
            return dict(trajectory=[dict(index=i,**{arm:dict(position=[0,0,.9],quaternion_wxyz=[1,0,0,0],
                gripper_closed=bool(row[j*7+6]<.5),gripper_opening=float(row[j*7+6])) for j,arm in enumerate(('left','right'))})
                for i,row in enumerate(kw['actions'])],measured_fk_check=dict(passed=True))
        if op in ('record_codex_decision','switch_control_source','finish_pilot'):return dict(physical_steps=0)
        if op=='chunk_step':
            rows=[]
            for action in kw['actions']:
                self.tick+=1;self.closed=action[13]<.5
                rows.append(dict(terminated=self.tick>=200,truncated=False,executed_action=action))
                if self.tick>=200:break
            return dict(step_id=self.tick,steps=rows)
        raise ValueError(op)
    def close(self):pass


class FakePolicy:
    def __init__(self,*args):self.index=0
    def infer(self,obs,path):
        actions=np.zeros((50,14),np.float32);actions[:,[6,13]]=1.
        info=dict(prediction_id=str(self.index),inference_index=self.index)
        self.index+=1
        return actions,info
    def close(self):pass


class FakeModel:
    def __init__(self,*args):self.calls=0;self.input_tokens=0
    def request(self,payload,remaining_s):
        self.calls+=1
        request=json.loads(payload['input'][0]['content'][0]['text'])['observation']
        return fake_decision(request)


class Tests(unittest.TestCase):
    def test_scheduler_factors_and_merged_events(self):
        empty=dict(phase_events=[],anomaly_events=[])
        event=dict(phase_events=['closure'],anomaly_events=['lost'])
        self.assertEqual(review_due(dict(periodic_review_max_steps=45,phase_trigger=False,anomaly_trigger=False),15,0,empty),[])
        self.assertEqual(review_due(dict(periodic_review_max_steps=15,phase_trigger=False,anomaly_trigger=False),15,0,empty),['periodic'])
        both=dict(periodic_review_max_steps=45,phase_trigger=True,anomaly_trigger=True)
        self.assertEqual(review_due(both,45,0,event),['periodic','phase:closure','anomaly:lost'])
        self.assertEqual(review_due(both,45,40,empty),[])

    def test_rgb_unknown_and_cooldown(self):
        monitor=Monitor(MONITOR);monitor.choose_arm('right')
        self.assertEqual(monitor.update(observation(visible=False),0)['anomaly_events'],[])
        s=monitor.update(observation(visible=False),5)
        self.assertIn('target_unobserved_two_acks',s['anomaly_events'])
        self.assertFalse(s['progress']['physical_grasp_verified'])
        self.assertEqual(monitor.update(observation(visible=False),10)['anomaly_events'],[])

    def test_failed_test_lift_and_motion_candidate(self):
        m=Monitor(MONITOR);m.choose_arm('right')
        m.update(observation(),0);m.update(observation(closed=True),5)
        r=m.update(observation(closed=True,rise=.025),10)
        self.assertIn('test_lift_without_visible_motion',r['anomaly_events'])
        self.assertIn('first_test_lift_observed',r['phase_events'])
        m=Monitor(MONITOR);m.choose_arm('right')
        m.update(observation(closed=True),0)
        r=m.update(observation(closed=True,rise=.025,pixel_shift=5),5)
        self.assertTrue(r['progress']['held_candidate'])
        self.assertFalse(r['progress']['physical_grasp_verified'])

    def test_original_failure_gate_rejects_uncertain_takeover(self):
        req=dict(request_id='r',step_id=0,gate_policy='failure-or-intent',current_eef={arm:dict(
            position=[0,0,.9],quaternion_wxyz=[1,0,0,0]) for arm in ('left','right')},
            student_eef_trajectory=[])
        raw=fake_decision(req);raw.update(mode='eef',target={arm:dict(position=[0,0,.9],
            quaternion_wxyz=[1,0,0,0],gripper_closed=False) for arm in ('left','right')})
        raw['assessment']['intent_status']='uncertain'
        with self.assertRaisesRegex(ValueError,'Takeover'):
            controller.adapt_decision(raw,req,15)
        raw['assessment']['intent_status']='misaligned'
        self.assertEqual(controller.adapt_decision(raw,req,15)[0]['mode'],'eef')
        raw['target']['right']['position']=[.06,0,.9]
        with self.assertRaisesRegex(ValueError,'5 cm'):
            controller.adapt_decision(raw,req,15)

    def test_development_image_localization(self):
        # Public RGB-only human annotation from layout1; no layout13 image used.
        path=ROOT/'tests/fixtures/shovel-layout1-cam-high.png'
        result=Monitor(MONITOR).detected(np.array(Image.open(path).convert('RGB')))
        x,y=result['centroid_px']
        self.assertTrue(450<=x<=500 and 189<=y<=286)
        self.assertFalse(result['identity_verified'])

    def test_refresh_is_fixed_across_all_five_schedulers(self):
        config=read(OWNED/'configs/part2-model.json')
        test_root=OWNED/'results/part2/offline-checks'
        test_root.mkdir(exist_ok=True,parents=True)
        for group in ['H11','S00','S10','S01','S11']:
            folder=Path(tempfile.mkdtemp(prefix=group+'-',dir=test_root))
            args=type('Args',(),dict(output=folder/'controller',config=OWNED/'configs/part2-model.json',
                group=group,layout=13,policy_port=1,checkpoint=Path('/offline'),sim_port=2))()
            with patch.object(controller,'Pi05Client',FakePolicy),patch.object(controller,'RPCClient',FakeSim),patch.object(controller,'Model',FakeModel):
                self.assertEqual(controller.run(args),'native_terminal')
            summary=read(folder/'controller/summary.json')
            self.assertEqual(summary['student_steps'],200)
            self.assertEqual(summary['vla_inferences'],14)
            identities=[read(p)['step_id'] for p in (folder/'controller/proposals').glob('*/identity.json')]
            self.assertEqual(sorted(identities),list(range(0,200,15)))
            if group=='H11':self.assertEqual(summary['review_count'],14)
            if group in ('S00','S10'):self.assertEqual(summary['review_count'],5)
            # Offline mock output never enters results/part2/records.jsonl.
            shutil.rmtree(folder)


if __name__=='__main__':unittest.main()
