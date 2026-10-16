"""Bounded, isolated single-case evaluation with explicit native outcomes."""
import argparse
import hashlib
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
from .common import ROOT,ASTRA,ROBODOJO,SIM_PYTHON,read,write,verify_case,sha
from .proxy import ModelProxy
from .budget_accounting import verify_budget_success

FRAMEWORK_METHODS = ('rpent_astra','gap_astra','phyagentos_official_astra','phyagentos_custom_astra')
POLICY_METHODS = ('pi05_only','pi05_discard_first','astra_hybrid','rpent_astra','phyagentos_official_astra')
MODULAR_METHODS = ('modular_pickup','modular_calibration','graspnet_calibration')
LANGUAGE_METHODS = ('astra_direct','astra_hybrid','astra_react_skill','modular_pickup',*FRAMEWORK_METHODS)


def stop(process):
    if process is None or process.poll() is not None:return
    os.killpg(process.pid,signal.SIGTERM)
    try:process.wait(timeout=12)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)


def run_case(case,method,config_path,split):
    verify_case(case)
    config=read(config_path)
    manipulation=config.get('hybrid_manipulation')
    policy_needed=method in POLICY_METHODS and not (
        method=='astra_hybrid' and manipulation and not manipulation['backend'].startswith('vla'))
    if manipulation:
        from .hybrid_manipulation import validate_settings
        validate_settings(manipulation)
        if method!='astra_hybrid' or config.get('hybrid_perception',{}).get('mode')!='raw_depth':
            raise ValueError('Manipulation comparison requires Astra hybrid with common raw-depth evidence')
    if method=='astra_react_skill':
        from .react_harness import load_bundle
        load_bundle(case['task'],use_skill=config.get('use_task_skill',True))
    identifier=datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-'+method+'-'+case['task']+'-l'+str(case['layout_id'])
    run=ROOT/'runs'/identifier;run.mkdir(parents=True)
    write(run/'case.json',case)
    if method in POLICY_METHODS and (ROOT/'openpi-runtime-preflight.json').exists():
        write(run/'policy_runtime.json',read(ROOT/'openpi-runtime-preflight.json'))
    write(run/'launch.json',dict(method=method,split=split,case=case,model_config_sha256=sha(config_path),
        adapter_files={p.name:sha(p) for p in (ROOT/'robot_agent_eval').glob('*.py')},model_config={k:v for k,v in config.items()
        if 'key' not in k},source_revision=read(ROOT/'source-lock.json')['astra_policy']['revision'],
        native_environment=read(ROOT/'manifests/inventory.json')['environment'],
        adapter=('Pinned original Astra native server and Pi05Client; execute first 15 of 50 predicted joint targets'
            if method in ('pi05_only','pi05_discard_first') else
            'Pinned original Astra server, prompts, Codex loop and bounded robot-only DLS; timing and provider wrappers'),
        observation_condition=('native three-camera RGB + robot proprio + instruction; no object truth or depth'
            if method in ('pi05_only','pi05_discard_first') else
            'native RGB + robot proprio + robot-only FK; no object truth, depth or layout contents'),
        budget_rule='all attempts retained; budget exhaustion is failure within budget and native outcome remains incomplete',
        calibration=method in ('hold_calibration','public_calibration','modular_calibration','graspnet_calibration')))
    if method in MODULAR_METHODS:
        receipt=ROOT/'results/sam3-download.json'
        if method=='modular_pickup' and (not receipt.exists() or not read(receipt).get('complete')):
            raise ValueError('Verified SAM3 checkpoint unavailable')
        launch=read(run/'launch.json')
        launch.update(adapter='Parameterised perception with configured local geometry or Contact-GraspNet backend and shared bounded DLS executor',
            observation_condition='public RGB-D/calibration; perception access determined by ablation condition; no scene truth',
            ablation=config.get('ablation'), public_rgbd_enabled=True, native_ik=method=='graspnet_calibration')
        write(run/'launch.json',launch)
        if method=='modular_pickup':write(run/'sam3_identity.json',read(receipt))
    if config.get('hybrid_perception'):
        if method!='astra_hybrid':raise ValueError('Perception main comparison requires Astra hybrid')
        from .hybrid_perception import validate_settings,COMMON_NOTE
        validate_settings(config['hybrid_perception'])
        launch=read(run/'launch.json')
        launch.update(hybrid_perception=config['hybrid_perception'],public_rgbd_enabled=True,
            method_condition='Astra hybrid with additive perception evidence; Astra schedules and authors every decision',
            perception_common_prompt_sha256=hashlib.sha256(COMMON_NOTE.encode()).hexdigest(),
            observation_condition='Same native RGB/proprio/pi05/FK; selected perception evidence only; raw sensors denied to agent',
            policy_observation_unchanged=True)
        write(run/'launch.json',launch)
    if manipulation:
        from .hybrid_manipulation import COMMON_NOTE
        launch=read(run/'launch.json')
        launch.update(hybrid_manipulation=manipulation,policy_enabled=policy_needed,
            method_condition='Astra manipulation-backend comparison; live task-derived grasp description',
            manipulation_common_prompt_sha256=hashlib.sha256(COMMON_NOTE.encode()).hexdigest(),
            gate_condition='failure-or-intent' if policy_needed else 'Astra planner; no VLA takeover gate',
            adapter='Persistent Astra with bounded EEF executor and configured live proposal backend')
        write(run/'launch.json',launch)
    if method=='astra_react_skill':
        from .react_harness import HARNESS,load_bundle
        shutil.copytree(HARNESS,run/'harness_snapshot')
        bundle=load_bundle(case['task'],use_skill=config.get('use_task_skill',True),root=run/'harness_snapshot')
        launch=read(run/'launch.json')
        launch.update(adapter='Compact Responses ReAct + task skill + unchanged Direct EEF/IK bridge',
                      harness={k:v for k,v in bundle.items() if k!='prompt'},
                      method_condition='task_skill' if config.get('use_task_skill',True) else 'generic_prompt_ablation')
        write(run/'launch.json',launch)
    if method=='pi05_discard_first':
        launch=read(run/'launch.json');launch['diagnostic_ablation']='Discard exactly one initial policy proposal, without any robot action, then use the same 15-step baseline'
        write(run/'launch.json',launch)
    if method in FRAMEWORK_METHODS:
        launch=read(run/'launch.json')
        launch.update(adapter='Native framework planner/tool/skill execution with local Responses and RoboDojo transport adapters',
            observation_condition='public RGB-D + calibration + robot proprio; no object truth or layout contents',
            framework_sources={k:v['revision'] for k,v in read(ROOT/'source-lock.json').items() if k in ('rpent','gap','gap_skills','phyagentos')},
            custom_skill=method=='phyagentos_custom_astra',sam3_available=False)
        if method=='gap_astra':
            for name in ('sam3','grounding-dino'):
                receipt=ROOT/'results'/f'{name}-download.json'
                if receipt.exists() and read(receipt).get('complete'):
                    write(run/f'{name}_identity.json',read(receipt))
                    launch[name.replace('-','_')+'_available']=True
        launch['native_ik']=method in ('rpent_astra','gap_astra')
        launch['public_rgbd_enabled']=True
        launch['native_idle_timeout_s']=config['max_episode_wall_s']+config['request_timeout_s']+60
        if method=='gap_astra' and config.get('gap_reuse_graph'):
            launch['method_condition']='generated_graph_replay_after_transport_fix'
            launch['prior_generation_graph']=config['gap_reuse_graph']
        write(run/'launch.json',launch)
    env=os.environ.copy()
    for name in ('OPENAI_API_KEY','OPENAI_BASE_URL','CODEX_API_KEY'):env.pop(name,None)
    env.update(PYTHONPATH=os.pathsep.join(map(str,(ROOT,ASTRA,ROBODOJO,ROBODOJO/'XPolicyLab',ROBODOJO/'third_party/curobo',ROOT/'source-snapshots/rpent'))),
        PYTHONNOUSERSITE='1',PYTHONUNBUFFERED='1',OMNI_KIT_ACCEPT_EULA='YES',
        ROBOT_EVAL_CASE_FILE=str(run/'case.json'),ROBODOJO_RUN_ID=identifier)
    env['ROBOT_EVAL_NATIVE_IK']='1' if method in ('rpent_astra','gap_astra','public_calibration','graspnet_calibration') else '0'
    env['ROBOT_EVAL_PUBLIC_RGBD']='1' if method in FRAMEWORK_METHODS or method in MODULAR_METHODS or method=='public_calibration' or config.get('hybrid_perception') else '0'
    env['ROBOT_EVAL_NATIVE_IDLE_TIMEOUT_S']=str(config['max_episode_wall_s']+config['request_timeout_s']+60)
    # Pick a free local RPC port. Do not probe-connect: the bridge has exactly one controller owner.
    import socket
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    simdir=run/'sim';simdir.mkdir();(simdir/'native_runtime').mkdir()
    simlog=(run/'sim.log').open('w');controllog=(run/'controller.log').open('w')
    sim=controller=proxy=policy=sam3=None;policylog=sam3log=None
    status='infrastructure_error';before=time.perf_counter();active=None;controller_started=None
    try:
        command=[SIM_PYTHON,'-m','robot_agent_eval.native_server','--task',case['task'],
            '--eval-seed',str(case['eval_seed']),'--output',str(simdir),'--port',str(port)]
        write(run/'commands.json',{'simulator':command})
        sim=subprocess.Popen(command,cwd=simdir/'native_runtime',env=env,stdout=simlog,stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.monotonic()+600
        while '"event": "ready"' not in (run/'sim.log').read_text(errors='replace'):
            if sim.poll() is not None:raise RuntimeError(f'Simulator exited before ready, rc={sim.returncode}')
            if time.monotonic()>deadline:raise TimeoutError('Simulator startup exceeded 600 seconds')
            time.sleep(1)
        write(run/'startup.json',dict(simulator_ready_s=time.perf_counter()-before))
        checkpoint=ROOT/'checkpoints/ckpt/RoboDojo/Pi_05/RoboDojo-sim-arx_x5-joint-0/59999'
        policy_python=Path(config.get('policy_python',ROOT/'.venvs/openpi-existing/bin/python'))
        if policy_needed:
            if not read(ROOT/'checkpoint-download-result.json')['complete']:
                raise ValueError('Checkpoint download/verification incomplete')
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));policy_port=sock.getsockname()[1]
            policylog=(run/'policy.log').open('w')
            policy_env=dict(env,XLA_PYTHON_CLIENT_PREALLOCATE='false',XLA_PYTHON_CLIENT_MEM_FRACTION='.45',
                PYTHONPATH=os.pathsep.join(map(str,(ROOT/'runtime-sources/openpi/src',
                    ROOT/'runtime-sources/openpi/packages/openpi-client/src')))+os.pathsep+env['PYTHONPATH'])
            policy_command=[str(policy_python),'-m','hybrid_rollout.robodojo.pi05_server.server',
                '--checkpoint',str(checkpoint),'--port',str(policy_port),'--identity-output',str(run/'policy_identity.json')]
            commands=read(run/'commands.json');commands['policy']=policy_command;write(run/'commands.json',commands)
            policy=subprocess.Popen(policy_command,cwd=run,env=policy_env,stdout=policylog,stderr=subprocess.STDOUT,start_new_session=True)
            deadline=time.monotonic()+600
            while not (run/'policy_identity.json').exists():
                if policy.poll() is not None:raise RuntimeError(f'Policy exited before load, rc={policy.returncode}')
                if time.monotonic()>deadline:raise TimeoutError('Policy load exceeded 600 seconds')
                time.sleep(1)
            startup=read(run/'startup.json');startup['all_services_ready_s']=time.perf_counter()-before
            write(run/'startup.json',startup)
        if method=='rpent_astra':
            receipt=ROOT/'results/sam3-download.json'
            if not receipt.exists() or not read(receipt).get('complete'):
                raise ValueError('Verified SAM3 checkpoint unavailable; RPent perception trial not started')
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));sam3_port=sock.getsockname()[1]
            sam3log=(run/'sam3.log').open('w')
            sam3_env=dict(env,SAM3_CHECKPOINT_PATH=str(ROOT/'checkpoints/sam3/sam3.pt'))
            sam3_command=[str(ROOT/'.venvs/frameworks/bin/python'),'-m','rpent.robots.components.sam3_server',
                '--transport','http','--host','127.0.0.1','--port',str(sam3_port)]
            commands=read(run/'commands.json');commands['sam3']=sam3_command;write(run/'commands.json',commands)
            sam3=subprocess.Popen(sam3_command,cwd=run,env=sam3_env,stdout=sam3log,stderr=subprocess.STDOUT,start_new_session=True)
            import urllib.request
            deadline=time.monotonic()+300
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            while True:
                if sam3.poll() is not None:raise RuntimeError('SAM3 server exited before readiness')
                if time.monotonic()>deadline:raise TimeoutError('SAM3 readiness exceeded 300 seconds')
                try:
                    request=urllib.request.Request(f'http://127.0.0.1:{sam3_port}/call',
                        data=b'{"method":"healthz","args":[],"kwargs":{},"session_id":null}',headers={'Content-Type':'application/json'})
                    with opener.open(request,timeout=1) as response:
                        if json.load(response).get('ok') is True:break
                except (OSError,ValueError):pass
                time.sleep(1)
            env['ROBOT_EVAL_SAM3_URL']=f'http://127.0.0.1:{sam3_port}'
            write(run/'sam3_identity.json',read(receipt))
            launch=read(run/'launch.json');launch['sam3_available']=True;write(run/'launch.json',launch)
        active=time.perf_counter()
        if method=='hold_calibration':
            command=[SIM_PYTHON,'-m','robot_agent_eval.hold_client','--port',str(port),'--layout',str(case['layout_id'])]
        elif method=='public_calibration':
            env['PYTHONPATH']+=os.pathsep+str(ROOT/'source-snapshots/phyagentos')
            command=[str(ROOT/'.venvs/frameworks/bin/python'),'-m','robot_agent_eval.public_calibration','--sim-port',str(port),
                '--layout',str(case['layout_id']),'--output',str(run/'controller')]
        elif method in MODULAR_METHODS:
            if method=='modular_pickup':
                proxy=ModelProxy(config,run/'model_requests.jsonl');env['ROBOT_REACT_PROXY_URL']=proxy.start()
            command=[str(ROOT/'.venvs/frameworks/bin/python'),'-m','robot_agent_eval.modular_pickup',
                '--method',method,'--sim-port',str(port),'--layout',str(case['layout_id']),
                '--output',str(run/'controller'),'--config',str(config_path.resolve())]
        elif method in ('pi05_only','pi05_discard_first'):
            command=[str(policy_python),'-m','robot_agent_eval.pi05_client','--sim-port',str(port),
                '--policy-port',str(policy_port),'--checkpoint',str(checkpoint),
                '--output',str(run/'controller'),'--layout',str(case['layout_id'])]
            if method=='pi05_discard_first':command+=['--discard-initial-proposals','1']
        elif method in FRAMEWORK_METHODS:
            proxy=ModelProxy(config,run/'model_requests.jsonl');url=proxy.start()
            env.update(ROBOT_REACT_PROXY_URL=url,GAP_SKILLS_PATH=str(ROOT/'source-snapshots/gap_skills'),GAP_LLM_NO_CACHE='1',LITELLM_LOCAL_MODEL_COST_MAP='True')
            env['PYTHONPATH']+=os.pathsep+os.pathsep.join(map(str,(ROOT/'source-snapshots/gap',
                ROOT/'source-snapshots/gap/gap-core/src',ROOT/'source-snapshots/phyagentos',
                ROOT/'runtime-sources/openpi/packages/openpi-client/src')))
            command=[str(ROOT/'.venvs/frameworks/bin/python'),'-m','robot_agent_eval.framework_controller',
                '--method',method,'--task',case['task'],'--sim-port',str(port),'--layout',str(case['layout_id']),
                '--output',str(run/'controller'),'--config',str(config_path.resolve())]
            if method in POLICY_METHODS:command+=['--policy-port',str(policy_port),'--checkpoint',str(checkpoint)]
        elif method=='astra_react_skill':
            proxy=ModelProxy(config,run/'model_requests.jsonl');url=proxy.start()
            env.update(ROBOT_REACT_PROXY_URL=url,ROBOT_REACT_HARNESS_DIR=str(run/'harness_snapshot'))
            command=[SIM_PYTHON,'-m','robot_agent_eval.react_harness','control','--task',case['task'],
                     '--sim-port',str(port),'--layout',str(case['layout_id']),
                     '--output',str(run/'controller'),'--config',str(config_path.resolve())]
        elif method in ('astra_direct','astra_hybrid'):
            proxy=ModelProxy(config,run/'model_requests.jsonl');url=proxy.start()
            # This home contains a loopback token only. Actual API credentials
            # stay in denied secrets/, while Codex runtime helpers can execute.
            home=run/'codex_runtime';home.mkdir(parents=True,mode=0o700)
            (home/'config.toml').write_text('model = "gpt-6-astra"\nmodel_provider = "OpenAI"\n'
                'model_reasoning_effort = "xhigh"\n[analytics]\nenabled = false\n'
                '[model_providers.OpenAI]\nname = "OpenAI"\nbase_url = '+json.dumps(url)+'\n'
                'wire_api = "responses"\nenv_key = "ROBOT_PROXY_TOKEN"\n')
            (home/'config.toml').chmod(0o600)
            env.update(CODEX_HOME=str(home),ROBOT_PROXY_TOKEN='loopback-eval-token',
                       ROBOT_EVAL_MODEL_CONFIG=str(config_path.resolve()))
            command=[SIM_PYTHON,'-m','robot_agent_eval.astra_controller','--task',case['task'],
                '--output',str(run/'controller'),'--evaluation-method',
                'pi05_plus_gpt' if method=='astra_hybrid' else 'gpt_only','--codex',shutil.which('codex'),
                '--sim-port',str(port),'--seed',str(case['layout_id']),'--max-decisions',str(config['max_decisions'])]
            if method=='astra_hybrid':
                command+=['--checkpoint',str(checkpoint)]
                if policy_needed:command+=['--student-port',str(policy_port)]
                env['PYTHONPATH']+=os.pathsep+str(ROOT/'runtime-sources/openpi/packages/openpi-client/src')
        else:raise ValueError('Unimplemented method: '+method)
        commands=read(run/'commands.json');commands['controller']=command;write(run/'commands.json',commands)
        controller_started=time.perf_counter()
        write(run/'controller_clock.json',dict(controller_started_monotonic=controller_started,
            budget_s=config['max_episode_wall_s'],deadline_monotonic=controller_started+config['max_episode_wall_s']))
        controller=subprocess.Popen(command,cwd=run,env=policy_env if method in ('pi05_only','pi05_discard_first') else env,
            stdout=controllog,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            rc=controller.wait(timeout=max(0,controller_started+config['max_episode_wall_s']-time.perf_counter()))
            status='controller_completed' if rc==0 else 'controller_error'
        except subprocess.TimeoutExpired:
            status='wall_budget';stop(controller)
        stop(sim)
    except Exception as error:
        write(run/'failure.json',dict(error_type=type(error).__name__,error=str(error)))
    finally:
        stop(controller);stop(sim);stop(policy);stop(sam3)
        if proxy:proxy.close()
        if policylog:policylog.close()
        if sam3log:sam3log.close()
        simlog.close();controllog.close()
        metadata=dict(status=status,process_wall_s=time.perf_counter()-before,
            controller_wall_s=time.perf_counter()-active if active else None,
            controller_started_monotonic=controller_started,
            simulator_exit_code=sim.returncode if sim else None,controller_exit_code=controller.returncode if controller else None)
        write(run/'process_result.json',metadata)
        result=make_result(run);write(run/'result.json',result)
    print(json.dumps(dict(run=str(run),**result),ensure_ascii=False),flush=True)
    return run,result


def make_result(run):
    launch=read(run/'launch.json');process=read(run/'process_result.json')
    outcome=read(run/'sim/evaluation_outcome.json') if (run/'sim/evaluation_outcome.json').exists() else {}
    timing=read(run/'sim/timing.json') if (run/'sim/timing.json').exists() else {}
    provenance=read(run/'controller/text_provenance.json') if (run/'controller/text_provenance.json').exists() else {}
    files=launch.get('adapter_files',{})
    implementation={k:v for k,v in files.items() if k in ('runner.py','native_server.py','framework_io.py','framework_controller.py',
        'rpent_adapter.py','gap_adapter.py','gap_compat.py','phyagentos_adapter.py','phyagentos_gateway.py','react_harness.py','astra_controller.py',
        'modular_pickup.py','ablation_perception.py','perception_pilot.py','graspnet_calibration.py','graspnet_probe.py','hybrid_perception.py','hybrid_manipulation.py','permissions.py','budget_accounting.py')}
    implementation_sha256=hashlib.sha256(json.dumps(implementation,sort_keys=True).encode()).hexdigest() if implementation else None
    calls=[json.loads(l) for l in (run/'model_requests.jsonl').read_text().splitlines()] if (run/'model_requests.jsonl').exists() else []
    starts=[json.loads(l) for l in (run/'model_request_starts.jsonl').read_text().splitlines()] if (run/'model_request_starts.jsonl').exists() else None
    native=bool(outcome.get('valid_for_success_rate'))
    budget_success,budget_basis,terminal_elapsed=verify_budget_success(native,outcome.get('native_success'),
        process,timing,launch.get('model_config',{}).get('max_episode_wall_s'))
    status=outcome.get('status',process['status'])
    if process['status']=='wall_budget':status='wall_budget'
    elif process['status']=='controller_error' and not native:status='controller_error'
    failure=read(run/'controller/failure.json') if (run/'controller/failure.json').exists() else {}
    journal=[json.loads(l) for l in (run/'sim/rpc_timing.jsonl').read_text().splitlines()] if (run/'sim/rpc_timing.jsonl').exists() else []
    recorded_steps=max([j.get('step_id',0) for j in journal]+[outcome.get('native_control_steps',0)])
    trace=(run/'controller/framework_trace.jsonl').read_text() if (run/'controller/framework_trace.jsonl').exists() else ''
    transport_lost=any(t in trace or t in failure.get('error','') for t in
        ('"event": "native_rpc_error"','RPC connection closed','RPC response identity mismatch','RPC client closed'))
    if not native and 'total-token budget reached' in failure.get('error',''):status='token_budget'
    if not native and any(c.get('error')=='model_call_budget' for c in calls):status='model_call_budget'
    if not native and 'Model call or total-token budget reached' in failure.get('error',''):
        count=len(starts) if starts is not None else len(calls)
        status='model_call_budget' if count>=launch.get('model_config',{}).get('max_model_calls_per_episode',float('inf')) else 'token_budget'
    started=(run/'sim/reset.json').exists()
    infrastructure=status in ('invalid_native_layout','reset_error','infrastructure_error') or not started
    if not native and transport_lost:
        status='native_transport_error';infrastructure=True
    elif not native and 'Model transport failed:' in failure.get('error',''):
        status='model_transport_error';infrastructure=True
    if (launch['method'] in FRAMEWORK_METHODS and process['status']=='controller_error'
            and not calls and not recorded_steps
            and not (run/'controller/adapter_ready.json').exists()):
        status='adapter_init_error';infrastructure=True
    deployment_stop=run/'controller/deployment_stop.json'
    if not native and deployment_stop.exists() and read(deployment_stop).get('status')=='adapter_contract_error':
        status='adapter_contract_error';infrastructure=True
    return dict(method=launch['method'],case_id=launch['case']['case_id'],split=launch['split'],
        harness_prompt_sha256=launch.get('harness',{}).get('prompt_sha256'),
        ablation=launch.get('ablation'),
        hybrid_perception=launch.get('hybrid_perception'),
        hybrid_manipulation=launch.get('hybrid_manipulation'),
        skill_id=launch.get('harness',{}).get('skill_id') or provenance.get('skill_name'),
        skill_sha256=provenance.get('skill_sha256'),implementation_sha256=implementation_sha256,
        status=status,model_config_sha256=launch.get('model_config_sha256'),episode_started=started,native_complete=native,
        native_success=outcome.get('native_success'),native_score=outcome.get('native_score'),
        success_within_budget=budget_success,budget_verification=budget_basis,
        terminal_controller_elapsed_s=terminal_elapsed,
        task_result_eligible=not infrastructure,calibration=launch['calibration'],
        native_steps=recorded_steps,native_limit=outcome.get('native_step_limit'),
        native_steps_source='native_outcome' if 'native_control_steps' in outcome else 'native_rpc_journal_lower_bound',
        timing=timing,process=process,model_requests=len(starts) if starts is not None else len(calls),
        model_requests_finished=len(calls),
        model_request_accounting=('not applicable; no language-model API' if launch['method'] not in LANGUAGE_METHODS else
            'submitted calls persisted before waiting' if starts is not None else
            'legacy completion logs only; interrupted in-flight requests may be missing'),
        model_usage_complete=(all(any(c.get('call')==s['call'] and c.get('usage') is not None for c in calls)
            for s in starts) if starts is not None else launch['method'] not in LANGUAGE_METHODS),
        model_wait_s=sum(c.get('elapsed_s',0) for c in calls),
        model_input_tokens=sum((c.get('usage') or {}).get('input_tokens',0) for c in calls),
        model_cached_input_tokens=sum(((c.get('usage') or {}).get('input_tokens_details') or {}).get('cached_tokens',0) for c in calls),
        model_output_tokens=sum((c.get('usage') or {}).get('output_tokens',0) for c in calls),
        cost=None,cost_note='Provider billing rates not supplied; token use retained, currency cost unknown')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--method',choices=('hold_calibration','public_calibration','modular_calibration','graspnet_calibration',*LANGUAGE_METHODS,'pi05_only','pi05_discard_first'),required=True)
    p.add_argument('--manifest',type=Path,default=ROOT/'manifests/calibration.json')
    p.add_argument('--task');p.add_argument('--layout',type=int);p.add_argument('--limit',type=int,default=1)
    p.add_argument('--config',type=Path,default=ROOT/'configs/model.local.json')
    a=p.parse_args();manifest=read(a.manifest)
    cases=[c for c in manifest['cases'] if (a.task is None or c['task']==a.task) and (a.layout is None or c['layout_id']==a.layout)]
    if not cases:raise ValueError('No matching frozen cases')
    for case in cases[:a.limit]:run_case(case,a.method,a.config,manifest['split'])


if __name__=='__main__':main()
