"""Offline transport contract tests; fixtures never count as benchmark trials."""
import asyncio
import sys
import base64
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import yaml
from robot_agent_eval.framework_io import responses_payload,PublicEnv
from robot_agent_eval.common import ROOT, source_path
sys.path.insert(0, str(ROOT / "source-snapshots/phyagentos"))
from robot_agent_eval.phyagentos_gateway import Gateway
from PhyAgentOS.forge.tool_client import ForgeToolClient, ForgeToolAPIError
from PhyAgentOS.forge.binding import ForgeSkillBindingResolver, ForgeSkillBindingError
from PhyAgentOS.skill_runtime.catalog import SkillCatalog
from PhyAgentOS.forge.task import _tool_status


class SensorFixture:
    tick=0
    ended=False
    def get_obs(self):
        return {'state':{f'{a}_{f}':np.zeros(n) for a in ('left','right') for f,n in [('arm_joint_state',6),('ee_joint_state',1)]}}


class Contracts(unittest.TestCase):
    def test_concurrent_observation_calls_preserve_real_rpc_packet_identity(self):
        source_path()
        from hybrid_rollout.robodojo.robodojo_server.protocol import RPCClient,receive_packet,send_packet,VERSION
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
        errors=[]
        def serve():
            try:
                conn,_=listener.accept()
                with conn:
                    conn.settimeout(5)
                    for _ in range(12):
                        request=receive_packet(conn);time.sleep(.003)
                        send_packet(conn,dict(version=VERSION,request_id=request['request_id'],ok=True,result=request['args']['tag']))
            except Exception as e:errors.append(e)
        server=threading.Thread(target=serve,daemon=True);server.start()
        with tempfile.TemporaryDirectory() as root:
            env=PublicEnv.__new__(PublicEnv);env.output=Path(root);env.tick=0;env.episode='fixture';env.rpc_lock=threading.RLock()
            env.rpc=RPCClient('127.0.0.1',listener.getsockname()[1],timeout=5)
            try:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    futures=[pool.submit(env.call,'public_observation',tag=i) for i in range(12)]
                    self.assertEqual([f.result() for f in futures],list(range(12)))
            finally:env.rpc.close();listener.close();server.join(timeout=5)
        self.assertFalse(errors)

    def test_function_history_and_image_survive_provider_conversion(self):
        messages=[{'role':'system','content':'official skill'},
                  {'role':'assistant','content':None,'tool_calls':[{'id':'call_1','function':{'name':'observe','arguments':'{}'}}]},
                  {'role':'tool','tool_call_id':'call_1','content':'public state'},
                  {'role':'user','content':[{'type':'image','source':{'media_type':'image/png','data':'AAAA'}}]}]
        p=responses_payload(messages,{'model':'gpt-6-astra','reasoning_effort':'xhigh'})
        self.assertEqual(p['instructions'],'official skill')
        self.assertEqual(p['input'][0]['call_id'],p['input'][1]['call_id'])
        self.assertEqual(p['input'][2]['content'][0]['image_url'],'data:image/png;base64,AAAA')

    def test_real_forge_client_binding_rejects_changed_specs_and_bad_arguments(self):
        async def exercise(root):
            env=SensorFixture();args=SimpleNamespace(output=root,layout=1,task='general_pickup')
            gateway=Gateway(env,None,args,False)
            client=ForgeToolClient(gateway.url)
            try:
                bundle=root/'skills/robodojo';bundle.mkdir(parents=True)
                (bundle/'SKILL.md').write_text('fixture document')
                (bundle/'dataflow.yaml').write_text('nodes: []')
                (bundle/'skill.yaml').write_text(yaml.safe_dump(dict(manifest_version=2,name='robodojo',version='0.2.1',
                    description='offline fixture',skill_document='SKILL.md',gateway_url=gateway.url,
                    required_tools=['bench.run'],profiles={'local_native_adapter':{'dataflow':'dataflow.yaml'}})))
                runtime=SimpleNamespace(skill_name='robodojo',skill_version='0.2.1',runtime_instance_id='test',profile='local_native_adapter',
                    gateway_identity='fixture',gateway_url=gateway.url,client=client)
                resolver=ForgeSkillBindingResolver(SimpleNamespace(current=lambda:runtime),catalog=SkillCatalog(root/'skills'))
                candidate=await resolver.preview('robodojo');binding=await resolver.freeze(candidate.candidate_id,task_id='test_task')
                with self.assertRaises(ForgeToolAPIError):
                    await client.invoke_action('bench.run',{'task_ids':[0]})
                self.assertIsNone(gateway.invocation)
                result=await client.invoke_action('bench.run',dict(task_ids=[0],init_state_ids=[1],num_runs=1,seed=0,max_steps=200))
                identifier=result['data']['invocation_id']
                status=await client.invocation_status(identifier)
                self.assertEqual(_tool_status(status,default='accepted'),'running')
                pending=await client.invocation_result(identifier)
                self.assertEqual(pending['data']['status'],'pending')
                with self.assertRaises(ForgeToolAPIError):
                    await client.invoke_action('bench.run',dict(task_ids=[0],init_state_ids=[1],num_runs=1,seed=0,max_steps=200))
                gateway.specs['bench.run']['description']+=' changed'
                with self.assertRaises(ForgeSkillBindingError):await resolver.validate_tool(binding,'bench.run','action')
                gateway.batch_result=lambda:dict(successes=0,total_episodes=1)
                env.ended=True
                terminal=await client.invocation_result(identifier)
                self.assertEqual(terminal['data']['status'],'available')
                self.assertEqual(_tool_status(terminal,default='accepted'),'succeeded')
                self.assertEqual(terminal['data']['result']['outputs']['successes'],0)
                self.assertEqual(_tool_status(await client.invocation_status(identifier),default='accepted'),'succeeded')
            finally:await client.close();gateway.close()
        with tempfile.TemporaryDirectory() as root:asyncio.run(exercise(Path(root)))

if __name__=='__main__':unittest.main()
