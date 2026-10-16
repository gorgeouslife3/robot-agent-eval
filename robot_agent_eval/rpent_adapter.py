"""RPent native RoboDojo toolkit with a new Responses planner provider."""
import json
import os
from pathlib import Path
import sys
import time
from .common import ROOT,write
from .framework_io import PublicEnv,RPentPolicy,ResponsesClient,responses_payload,chat_reply,append_trace


def run(args,config):
    sys.path.insert(0,str(ROOT/'source-snapshots/rpent'))
    from robots.robodojo.toolkit import RoboDojoToolkit
    from robots.robodojo.prompt_bundle import system_prompt,user_prompt
    from rpent.prompt.utils import format_prompt
    from rpent.prompt.common import OUTPUT
    from rpent.memory.manager import MemoryManager
    from rpent.utils.logging import init_output_dir
    init_output_dir(args.output)
    class Sink:
        def emit(self,event):pass
    env=PublicEnv(args.sim_port,args.layout,args.output,'rpent_astra')
    try:
        _run(args,config,env)
    finally:env.close()


def _run(args,config,env):
    from robots.robodojo.toolkit import RoboDojoToolkit
    from robots.robodojo.prompt_bundle import system_prompt,user_prompt
    from rpent.prompt.utils import format_prompt
    from rpent.prompt.common import OUTPUT
    from rpent.memory.manager import MemoryManager
    class Sink:
        def emit(self,event):pass
    memory=MemoryManager(ROOT/'source-snapshots/rpent/memory/robodojo')
    policy=RPentPolicy(args)
    try:
        _plan(args,config,env,memory,policy,Sink())
    finally:policy.close()


def _plan(args,config,env,memory,policy,sink):
    from robots.robodojo.toolkit import RoboDojoToolkit
    from robots.robodojo.prompt_bundle import system_prompt,user_prompt
    from rpent.prompt.utils import format_prompt
    from rpent.prompt.common import OUTPUT
    from rpent.robots.components.sam3_client import Sam3Client
    from rpent.utils.rpc.http_rpc import HttpRpcClient
    sam3_url=os.environ.get('ROBOT_EVAL_SAM3_URL')
    sam3=Sam3Client(HttpRpcClient(sam3_url)) if sam3_url else None
    toolkit=RoboDojoToolkit(primitives_kwargs={'env':env,'sam3_client':sam3,'vla_client':policy,'task':args.task,'action_type':'joint'},
        dashboard_events=sink,memory=memory)
    variables=dict(task=args.task,layout=args.layout,env_cfg_type='arx_x5',action_type='joint',output_dir=str(args.output),task_summary='')
    system=format_prompt(system_prompt(variables),variables=variables)+'\n'+format_prompt(OUTPUT,variables=variables)
    user=format_prompt(user_prompt(variables),variables=variables)
    write(args.output/'text_provenance.json',dict(framework='RPent',system_sources=['robots/robodojo/prompts/system.py','rpent/prompt/common.py'],
        user_source='robots/robodojo/prompts/user.py',skills_used=[],prior_custom_shovel_skill=False,
        memory_root=str(memory.root),memory_available=memory.root.exists(),sam3_available=sam3 is not None,vla_available=True,provider_adapter='new Responses planner; native RPent toolkit retained'))
    (args.output/'SYSTEM.md').write_text(system);(args.output/'USER.md').write_text(user)
    write(args.output/'adapter_ready.json',dict(method=args.method,sam3=sam3 is not None))
    model=ResponsesClient(config,args.output);messages=[dict(role='system',content=system),dict(role='user',content=user)]
    for i in range(config['max_model_calls_per_episode']):
        response=model.request(responses_payload(messages,config,toolkit.get_tools_spec()))
        reply=chat_reply(response)['choices'][0]['message'];messages.append(reply)
        if not reply.get('tool_calls'):break
        for tc in reply['tool_calls']:
            before=time.perf_counter();arguments=json.loads(tc['function']['arguments']);start=env.tick
            result=toolkit.execute_tool(tc['function']['name'],arguments)
            append_trace(args.output,dict(sequence=i,tool=tc['function']['name'],arguments=arguments,start_step=start,end_step=env.tick,
                elapsed_s=time.perf_counter()-before,result={k:v for k,v in result.result.items() if not k.startswith('_image')}))
            # Responses function outputs are text, followed by the same
            # image blocks RPent's ToolResult supplies to other planners.
            texts=[b['text'] for b in result.content_blocks if b['type']=='text']
            messages.append(dict(role='tool',tool_call_id=tc['id'],content='\n'.join(texts)))
            images=[b for b in result.content_blocks if b['type']=='image']
            if images:messages.append(dict(role='user',content=images))
            if result.is_finish or env.ended:return
