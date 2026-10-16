"""Hold observed initial joints through the native horizon: infrastructure only."""
import argparse
import numpy as np
from .common import source_path


def main():
    source_path()
    from hybrid_rollout.robodojo.robodojo_server.protocol import RPCClient
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,required=True);p.add_argument('--layout',type=int,required=True)
    a=p.parse_args();client=RPCClient('127.0.0.1',a.port,timeout=600)
    try:
        reset=client.request('reset',seed=a.layout,source='student',policy_version='hold_calibration')
        episode=reset['episode_id'];tick=0
        obs=client.request('teacher_observation',episode_id=episode,step_id=tick)
        hold=np.asarray(obs['states'],np.float32)
        while True:
            result=client.request('chunk_step',episode_id=episode,step_id=tick,actions=np.tile(hold,(15,1)))
            tick=result['step_id'];row=result['steps'][-1]
            print(f'hold control steps: {tick}',flush=True)
            if row['terminated'] or row['truncated']:break
        client.request('finish_pilot',episode_id=episode,step_id=tick,reason='terminal')
    finally:client.close()


if __name__=='__main__':main()
