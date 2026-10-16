"""Queue only the latest part-2 task; own outputs and process groups only."""
import argparse
import fcntl
import os
from pathlib import Path
import signal
import shutil
import socket
import subprocess
import sys
import time

from support import ROOT, OWNED, append, implementation_identity, now, owned, read, sha, write

from robot_agent_eval.common import SIM_PYTHON, ROBODOJO
POLICY_PYTHON=str(ROOT/'.venvs/openpi-existing/bin/python')
CHECKPOINT=ROOT/'checkpoints/ckpt/RoboDojo/Pi_05/RoboDojo-sim-arx_x5-joint-0/59999'
RESULTS=OWNED/'results/part2'


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


def stop_owned(process):
    if process is None or process.poll() is not None:return
    os.killpg(process.pid,signal.SIGTERM)
    try:process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)


def wait_ready(process,path,predicate,deadline_s=600):
    deadline=time.monotonic()+deadline_s
    while True:
        if process.poll() is not None:
            raise RuntimeError('Owned service exited before readiness: '+str(process.returncode))
        if path.exists() and predicate(path):return
        if time.monotonic()>=deadline:raise TimeoutError('Owned service readiness timeout')
        time.sleep(1)


def run_one(item,config_path):
    # Neither the old runner nor its aggregate commands are called.
    from robot_agent_eval.proxy import ModelProxy
    config=read(config_path)
    case=read(OWNED/'manifests/part2-case.json')['cases'][0]
    run=owned(OWNED/'runs/part2'/f'r{item["repeat_id"]}-{item["group_id"]}')
    run.mkdir(parents=True,exist_ok=False)
    write(run/'case.json',case)
    write(run/'launch.json',dict(item,case_id=case['case_id'],method='astra_hybrid',
        config_sha256=sha(config_path),implementation=implementation_identity(),
        prompt_sha256=sha(OWNED/'configs/hybrid-prompt.md'),started_at=now(),
        model_config={k:v for k,v in config.items() if 'key' not in k}))
    (run/'sim/native_runtime').mkdir(parents=True)
    (run/'cache').mkdir()
    env=os.environ.copy()
    for variable in ('OPENAI_API_KEY','CODEX_API_KEY','OPENAI_BASE_URL'):env.pop(variable,None)
    env.update(PYTHONPATH=os.pathsep.join(map(str,[ROOT,ROOT/'source-snapshots/astra_policy',
        ROBODOJO,ROBODOJO/'XPolicyLab',
        ROBODOJO/'third_party/curobo'])),
        PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',PYTHONUNBUFFERED='1',OMNI_KIT_ACCEPT_EULA='YES',
        ROBOT_EVAL_CASE_FILE=str(run/'case.json'),ROBODOJO_RUN_ID='supervision-part2-'+run.name,
        ROBOT_EVAL_NATIVE_IK='0',ROBOT_EVAL_PUBLIC_RGBD='0',ROBOT_EVAL_NATIVE_IDLE_TIMEOUT_S='1440',
        TMPDIR=str(run/'cache'),XDG_CACHE_HOME=str(run/'cache/xdg'),
        HF_HOME=str(run/'cache/hf'),TORCH_HOME=str(run/'cache/torch'),
        MPLCONFIGDIR=str(run/'cache/matplotlib'),CUDA_CACHE_PATH=str(run/'cache/cuda'),
        OPENPI_DATA_HOME=str(run/'cache/openpi'),JAX_COMPILATION_CACHE_DIR=str(run/'cache/jax'))
    # Seed an owned tokenizer cache from existing read-only bytes, if present.
    # Do not hardlink: the library is allowed to change cache permissions.
    tokenizer=Path(os.environ.get('ROBOT_EVAL_TOKENIZER', Path.home()/'.cache/openpi/big_vision/paligemma_tokenizer.model'))
    if tokenizer.exists():
        copied=run/'cache/openpi/big_vision/paligemma_tokenizer.model'
        copied.parent.mkdir(parents=True);shutil.copyfile(tokenizer,copied)
    policy_env=dict(env,XLA_PYTHON_CLIENT_PREALLOCATE='false',XLA_PYTHON_CLIENT_MEM_FRACTION='.45',
        PYTHONPATH=os.pathsep.join(map(str,[ROOT/'runtime-sources/openpi/src',
            ROOT/'runtime-sources/openpi/packages/openpi-client/src']))+os.pathsep+env['PYTHONPATH'])
    sim_port=port();policy_port=port()
    sim=policy=controller=proxy=None
    logs=[];status='infrastructure_error';error=None;before=time.perf_counter()
    try:
        sim_log=(run/'sim.log').open('w');logs.append(sim_log)
        command=[SIM_PYTHON,'-m','robot_agent_eval.native_server','--task',case['task'],
            '--eval-seed',str(case['eval_seed']),'--output',str(run/'sim'),'--port',str(sim_port)]
        write(run/'commands.json',dict(simulator=command))
        sim=subprocess.Popen(command,cwd=run/'sim/native_runtime',env=env,
            stdout=sim_log,stderr=subprocess.STDOUT,start_new_session=True)
        wait_ready(sim,run/'sim.log',lambda p:'"event": "ready"' in p.read_text(errors='replace'))
        policy_log=(run/'policy.log').open('w');logs.append(policy_log)
        command=[POLICY_PYTHON,'-m','hybrid_rollout.robodojo.pi05_server.server',
            '--checkpoint',str(CHECKPOINT),'--port',str(policy_port),'--identity-output',str(run/'policy_identity.json')]
        commands=read(run/'commands.json');commands['policy']=command;write(run/'commands.json',commands)
        policy=subprocess.Popen(command,cwd=run,env=policy_env,stdout=policy_log,
            stderr=subprocess.STDOUT,start_new_session=True)
        wait_ready(policy,run/'policy_identity.json',lambda p:True)
        write(run/'startup.json',dict(services_ready_s=time.perf_counter()-before))
        proxy=ModelProxy(config,run/'model_requests.jsonl')
        env['ROBOT_SUPERVISION_PROXY_URL']=proxy.start()
        control_log=(run/'controller.log').open('w');logs.append(control_log)
        command=[SIM_PYTHON,str(OWNED/'implementation/controller.py'),'--sim-port',str(sim_port),
            '--policy-port',str(policy_port),'--checkpoint',str(CHECKPOINT),'--output',str(run/'controller'),
            '--config',str(config_path),'--group',item['group_id'],'--layout',str(case['layout_id'])]
        commands=read(run/'commands.json');commands['controller']=command;write(run/'commands.json',commands)
        controller=subprocess.Popen(command,cwd=run,env=env,stdout=control_log,
            stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.perf_counter()+600
        while controller.poll() is None:
            if (run/'active_clock.json').exists():
                deadline=read(run/'active_clock.json')['start_monotonic']+config['max_episode_wall_s']+30
            if time.perf_counter()>deadline:
                status='controller_watchdog';break
            if sim.poll() is not None:
                status='native_transport_error';break
            time.sleep(1)
        else:
            status='controller_finished' if controller.returncode==0 else 'controller_error'
    except Exception as exception:
        error=dict(error_type=type(exception).__name__,error=str(exception))
        write(run/'failure.json',error)
    finally:
        # These handles were created above. No search/kill of another task.
        stop_owned(controller);stop_owned(sim);stop_owned(policy)
        if proxy:proxy.close()
        for handle in logs:handle.close()
        write(run/'process.json',dict(status=status,error=error,process_wall_s=time.perf_counter()-before,
            controller_exit=controller.returncode if controller else None,
            simulator_exit=sim.returncode if sim else None,policy_exit=policy.returncode if policy else None))
    from report import summarize_run
    result=summarize_run(run)
    write(run/'result.json',result)
    return result


def alive(pid):
    try:
        os.kill(pid,0)
        return Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()[0]!='Z'
    except ProcessLookupError:return False
    except FileNotFoundError:return False


def gpu_is_idle():
    result=subprocess.run(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],
        capture_output=True,text=True,timeout=10)
    return result.returncode==0 and not result.stdout.strip()


def current_immutable_changes():
    frozen=read(OWNED/'configs/part2-freeze.json')
    return [name for name,digest in frozen['immutable_dependencies'].items()
        if not (ROOT/name).is_file() or sha(ROOT/name)!=digest]


def launch_queue():
    from report import generate
    frozen=read(OWNED/'configs/part2-freeze.json')
    lock=owned(OWNED/'results/part2/queue.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    state_path=RESULTS/'state.json'
    if state_path.exists():
        state=read(state_path)
    else:
        state=dict(experiment_id=frozen['experiment_id'],status='queued',queued_at=now(),
            queue_pid=os.getpid(),wait_for_pid=frozen['wait_for_pid'],schedule=frozen['schedule'],records=[],current=None)
    state.update(queue_pid=os.getpid())
    write(state_path,state);generate(state)
    # Polling never consumes the GPU and never writes the old lock file.
    while alive(frozen['wait_for_pid']) or not gpu_is_idle():
        time.sleep(30)
    legacy=None
    legacy_path=ROOT/'results/classic-hybrid-gpu.lock'
    if legacy_path.exists():
        legacy=legacy_path.open('r')
        fcntl.flock(legacy,fcntl.LOCK_EX)
    try:
        changes=current_immutable_changes()
        if changes:raise RuntimeError('Frozen dependency changed: '+', '.join(changes))
        actual=implementation_identity()
        if actual!=frozen['implementation']:raise RuntimeError('Queued implementation changed after freeze')
        if sha(OWNED/'configs/part2-model.json')!=frozen['model_config_sha256']:
            raise RuntimeError('Queued model config changed after freeze')
        if sha(OWNED/'configs/hybrid-prompt.md')!=frozen['prompt_sha256']:
            raise RuntimeError('Queued prompt changed after freeze')
        if sha(OWNED/'manifests/part2-case.json')!=frozen['case_manifest_sha256']:
            raise RuntimeError('Queued case changed after freeze')
        if sha(OWNED/'manifests/part2-schedule.json')!=frozen['schedule_sha256']:
            raise RuntimeError('Queued schedule changed after freeze')
        state.update(status='running',started_at=now());write(state_path,state);generate(state)
        for item in state['schedule']:
            if any(r['schedule_index']==item['schedule_index'] for r in state['records']):continue
            while not gpu_is_idle():
                state.update(status='waiting_for_gpu',current=None)
                write(state_path,state);generate(state);time.sleep(30)
            state['status']='running'
            state['current']=dict(item,started_at=now());write(state_path,state);generate(state)
            result=run_one(item,OWNED/'configs/part2-model.json')
            row=dict(item,result=result)
            state['records'].append(row);state['current']=None
            append(RESULTS/'records.jsonl',row);write(state_path,state);generate(state)
            if len(state['records'])>=3 and all(r['result']['native_steps']==0 for r in state['records'][-3:]):
                raise RuntimeError('Three consecutive zero-step failures; retained results and stopped deployment')
        state.update(status='complete',completed_at=now(),immutable_changes=current_immutable_changes())
    except Exception as error:
        state.update(status='stopped',stop_reason=str(error),stopped_at=now())
    finally:
        state['current']=None;write(state_path,state);generate(state)
        if legacy:fcntl.flock(legacy,fcntl.LOCK_UN);legacy.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--queue',action='store_true',required=True)
    parser.parse_args();launch_queue()
