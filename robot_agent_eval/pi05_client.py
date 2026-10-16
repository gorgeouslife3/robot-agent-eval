"""π0.5-only reference: same native bridge, 15 executed steps per inference."""
import argparse
from pathlib import Path
from .common import source_path,write


def main():
    source_path()
    from hybrid_rollout.robodojo.pi05_server.client import Pi05Client
    from hybrid_rollout.robodojo.robodojo_server.protocol import RPCClient
    p=argparse.ArgumentParser();p.add_argument('--sim-port',type=int,required=True)
    p.add_argument('--policy-port',type=int,required=True);p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--layout',type=int,required=True)
    p.add_argument('--discard-initial-proposals',type=int,choices=(0,1),default=0,
        help='Diagnostic ablation: discard one initial inference at the unchanged scene')
    a=p.parse_args();a.output.mkdir(parents=True)
    policy=Pi05Client(a.policy_port,a.checkpoint);sim=RPCClient('127.0.0.1',a.sim_port,timeout=600)
    timings=[]
    try:
        reset=sim.request('reset',seed=a.layout,source='student',policy_version='pi05_only')
        episode=reset['episode_id'];tick=0
        while True:
            obs=sim.request('teacher_observation',episode_id=episode,step_id=tick)
            actions,record=policy.infer(obs,a.output/f'prediction_{len(timings):03d}.npz')
            record.update(observation_step=tick,executed=len(timings)>=a.discard_initial_proposals)
            timings.append(record);write(a.output/'inference_timing.json',timings)
            if not record['executed']:
                print('Discarded first proposal at unchanged initial observation; zero robot controls',flush=True)
                continue
            result=sim.request('chunk_step',episode_id=episode,step_id=tick,actions=actions[:15])
            tick=result['step_id'];row=result['steps'][-1]
            print(f'pi05 control steps: {tick}',flush=True)
            if row['terminated'] or row['truncated']:break
        sim.request('finish_pilot',episode_id=episode,step_id=tick,reason='terminal')
    finally:sim.close();policy.close()


if __name__=='__main__':main()
