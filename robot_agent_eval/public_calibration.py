"""Native transport/IK calibration, never a scored robot-agent attempt."""
import argparse
import asyncio
from pathlib import Path
import time
from .framework_io import PublicEnv
from .phyagentos_gateway import Gateway
from .common import write

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--sim-port',type=int);p.add_argument('--layout',type=int);p.add_argument('--output',type=Path)
    args=p.parse_args();args.task='general_pickup';args.output.mkdir(parents=True)
    env=PublicEnv(args.sim_port,args.layout,args.output,'public_calibration');gateway=None
    try:
        gateway=Gateway(env,None,args,True)
        before=gateway.observation()
        command=dict(stage='approach',evidence='Calibration: hold measured pose',expected_effect='Hold without translation',
            next_check='Read fresh public sensors',memory={'grasp_verified':False,'facts':[]},arm='right',
            translation_m=[0.,0.,0.],rotation_xyz_deg=[0.,0.,0.],gripper='keep',control_steps=1)
        gateway.dispatch('POST','/tools/robot.delta_action:invoke',{'arguments':command})
        time.sleep(2)
        gateway.dispatch('POST','/tools/robot.delta_action:invoke',{'arguments':command})
        # Full-pose and position-only IK are planning queries; no extra motion.
        after=gateway.observation()
        q=after['current_eef']['right'];ik=env.solve_pose('right',q['position']+q['quaternion_wxyz'])
        pos=env.solve_ik_position('right',q['position'])
        import numpy as np
        def plain(value):
            if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
            if isinstance(value,(list,tuple)):return [plain(v) for v in value]
            return value.tolist() if isinstance(value,np.ndarray) else value
        write(args.output/'calibration.json',plain(dict(controls=env.tick,full_pose_ik=ik,position_ik=pos,public_before=before,public_after=after)))
    finally:
        if gateway:gateway.close()
        env.close()

if __name__=='__main__':main()
