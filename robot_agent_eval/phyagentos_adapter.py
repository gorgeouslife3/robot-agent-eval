"""Native PAOS AgentLoop, task binding and verification with local transports."""
import asyncio
import json
from pathlib import Path
import shutil
import threading
import time
from types import SimpleNamespace
import uuid
import yaml
from .common import ROOT, write, sha
from .framework_io import PublicEnv, RPentPolicy, ResponsesClient, responses_payload, chat_reply, append_trace
from .phyagentos_gateway import Gateway


def run(args, config):
    from PhyAgentOS.agent.loop import AgentLoop
    from PhyAgentOS.providers.base import LLMProvider, LLMResponse, ToolCallRequest
    from PhyAgentOS.agent.tools.image import ImageTool
    from PhyAgentOS.agent.session_verifier import ForgeTaskVerifier
    from PhyAgentOS.verification.service import FORGE_TASK_PROMPT
    from PhyAgentOS.bus.queue import MessageBus
    from PhyAgentOS.config.schema import ForgeConfig, ForgeEvidenceConfig
    from PhyAgentOS.forge.tool_client import ForgeToolClient
    from PhyAgentOS.forge.binding import ForgeSkillBindingResolver
    from PhyAgentOS.forge.task import AgentTaskCoordinator
    from PhyAgentOS.forge.observation import ObservationSnapshot, CapturedImage, CapturedState, utc_now
    from PhyAgentOS.skill_runtime.catalog import SkillCatalog

    custom=args.method=='phyagentos_custom_astra'
    env=policy=gateway=None
    workspace=args.output/'workspace';workspace.mkdir(parents=True)
    model=ResponsesClient(config,args.output);model_lock=threading.Lock()

    class Provider(LLMProvider):
        def get_default_model(self):return config['model']
        async def chat(self,messages,tools=None,model=None,**kwargs):
            if env is not None and env.rpc.sock is None:
                raise RuntimeError('Native transport lost; this deployment attempt cannot continue')
            payload=responses_payload(messages,config,tools)
            # Images, verification, and planning share one episode budget.
            def request():
                with model_lock:return model_client.request(payload)
            response=await asyncio.to_thread(request)
            reply=chat_reply(response)['choices'][0]['message']
            return LLMResponse(content=reply['content'],tool_calls=[ToolCallRequest(id=t['id'],name=t['function']['name'],
                arguments=json.loads(t['function']['arguments'])) for t in reply.get('tool_calls',[])],usage=response['usage'])
        async def chat_with_retry(self,**kwargs):
            kwargs.pop('mode',None)
            return await self.chat(**kwargs)  # no hidden provider retries
    model_client=model;provider=Provider()

    class Verifier(ForgeTaskVerifier):
        def _start_and_verify(self,content):
            return asyncio.run(self.engine.complete(system_prompt=FORGE_TASK_PROMPT,content=content))

    class Collector:
        errors=[]
        async def start(self):pass
        async def close(self):pass
        async def wait_for_before(self,*a,**kw):return self.capture()
        async def wait_for_after(self,*a,**kw):return self.capture()
        def capture(self):
            with gateway.lock:
                obs=gateway.observation();now=utc_now()
                return ObservationSnapshot(captured_at=now,images={x['camera']:CapturedImage(source_id=x['camera'],
                    sequence=gateway.capture_seq,captured_at=now.timestamp(),received_at=now,media_type='image/png',data=Path(x['path']).read_bytes())
                    for x in obs['images']},state=CapturedState(received_at=now,payload=obs['current_state']))
    class Coordinator(AgentTaskCoordinator):
        def _collector(self,task):return Collector()

    async def execute():
        client=ForgeToolClient(gateway.url,timeout_s=180)
        try:
            name='phyagentos-shovel-pickup' if custom else 'robodojo'
            skill_source=(ROOT/'harness/skills/phyagentos-shovel-pickup/SKILL.md' if custom else ROOT/'runtime-sources/phyagentos-robodojo-skill/SKILL.md')
            bundle=workspace/'skills'/name;bundle.mkdir(parents=True)
            shutil.copy2(skill_source,bundle/'SKILL.md')
            (bundle/'local-dataflow.yaml').write_text('nodes: []\n')
            manifest=dict(manifest_version=2,name=name,version='0.1.0' if custom else '0.2.1',
                description='Local RoboDojo adapter condition',skill_document='SKILL.md',gateway_url=gateway.url,
                required_tools=list(gateway.specs),profiles={'local_native_adapter':{'dataflow':'local-dataflow.yaml'}})
            (bundle/'skill.yaml').write_text(yaml.safe_dump(manifest,sort_keys=False))
            catalog=SkillCatalog(root=workspace/'skills')
            runtime=SimpleNamespace(skill_name=name,skill_version=manifest['version'],profile='local_native_adapter',
                runtime_instance_id='local_'+uuid.uuid4().hex,gateway_url=gateway.url,gateway_identity='local-native-robodojo',client=client)
            binding=ForgeSkillBindingResolver(SimpleNamespace(current=lambda:runtime),catalog=catalog)
            verifier=Verifier(workspace=workspace,provider=provider,model=config['model'],evidence_retention='all',max_calls=4,write_legacy_lessons=False)
            coordinator=Coordinator(workspace=workspace,config=ForgeConfig(request_timeout_s=180,
                evidence=ForgeEvidenceConfig(required_image_sources=['cam_head','cam_left_wrist','cam_right_wrist'])),
                client=client,verifier=verifier,binding_resolver=binding)
            loop=AgentLoop(bus=MessageBus(),provider=provider,workspace=workspace,model=config['model'],
                max_iterations=config['max_model_calls_per_episode'],context_window_tokens=1000000,
                forge_tool_client=client,forge_task_coordinator=coordinator,restrict_to_workspace=True,
                runtime_availability_provider=lambda n:n==name)
            # Run-local catalogs keep unrelated user-installed skills out of this condition.
            loop.context.skills.installed_skills=workspace/'skills'
            loop.skill_activation.skills.installed_skills=workspace/'skills'
            for tool_name in list(loop.tools.tool_names):
                if tool_name in ('exec','web_search','web_fetch','message','spawn','cron','write_file','edit_file','scene_graph_query'):
                    loop.tools.unregister(tool_name)
            loop.tools.register(ImageTool(provider))
            original=loop.tools.execute
            async def tool_execute(name,arguments):
                before=time.perf_counter();start=env.tick
                result=await original(name,arguments)
                append_trace(args.output,dict(event='phyagentos_tool',tool=name,arguments=arguments,start_step=start,
                    end_step=env.tick,elapsed_s=time.perf_counter()-before,result=result))
                return result
            loop.tools.execute=tool_execute
            prompt=env.observation['instruction']+f'\nUse the {name} skill as primary. This is one frozen evaluation episode: general_pickup, task_ids=[0], init_state_ids=[{args.layout}], num_runs=1, seed=0, max_steps=200. All calls, image analysis, verification and actions count toward one budget. The robot and sensor bridge is already ready. Do not reset or start a second batch.'
            if not custom:
                prompt+='\nThe installed supervisor profile is gpt6_pi05: query the live vla tools and current image files, inspect images with image(vision), then use vla.decide(student/edit/stop) or vla.set_mode. This joint-action profile supports joint edits, not direct EEF commands. The original BridgeState checks segment and edit limits.'
            (args.output/'USER.md').write_text(prompt)
            write(args.output/'text_provenance.json',dict(framework='PhyAgentOS-core',skill_name=name,skill_source=str(skill_source),
                skill_sha256=sha(skill_source),official_skill=not custom,prior_custom_shovel_skill=False,
                custom_skill_derivation='robodojo-shovel-pickup' if custom else None,
                system_sources=['PhyAgentOS/agent/context.py','PhyAgentOS/agent/skills.py','PhyAgentOS/verification/service.py'],
                manifest_adapter='Released profile required_tools moved to run-local manifest root; local transport profile replaces Dora launch',
                retained=['AgentLoop','SkillActivationManager','ForgeSkillBindingResolver','AgentTaskCoordinator','ForgeTaskVerifier verdict validation','BridgeState (official condition)'],
                adaptations=['Responses provider','local HTTP Gateway execution','public native evidence collector','in-process verifier transport'],
                tools=loop.tools.tool_names,sam3_available=False,vla_available=not custom))
            write(args.output/'adapter_ready.json',dict(method=args.method,skill=name,gateway=gateway.url))
            final=await loop.process_direct(prompt,session_key='eval:single',channel='eval',chat_id='single')
            (args.output/'FINAL.md').write_text(final or '')
            active=coordinator.store.active()
            if active:write(args.output/'active_agent_task.json',active.model_dump(mode='json'))
            verifier.stop()
        finally:await client.close()
    try:
        env=PublicEnv(args.sim_port,args.layout,args.output,args.method)
        policy=None if custom else RPentPolicy(args)
        gateway=Gateway(env,policy,args,custom)
        asyncio.run(execute())
    finally:
        if gateway:gateway.close()
        if env:env.close()
        if policy:policy.close()
