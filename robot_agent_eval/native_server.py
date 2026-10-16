"""Instrument the pinned Astra native bridge without editing upstream files.

Reward predicates, action stepping, settling and robot-only IK remain upstream.
The evaluator supplies an explicit locked case; the agent receives no layout data.
"""
import json
import os
from pathlib import Path
import sys
import signal
import time
from .common import read, source_path, verify_case, write


def enable_public_rgbd(cfg):
    """Enable native depth sensors and calibration, without scene-state access."""
    vision=cfg.eval_cfg.observation.vision
    vision.depth=True;vision.approximate_depth=False
    vision.intrinsic_matrix=True;vision.extrinsic_matrix=True
    for capture in cfg.camera.annotator.values():
        capture.enabled=True
        capture.distance_to_image_plane_capture=dict(type='distance_to_image_plane',device='cpu')


def main():
    def shutdown(signum,frame):
        write(Path(sys.argv[sys.argv.index('--output')+1])/'shutdown_signal.json',dict(signal=signum,time_monotonic=time.perf_counter()))
        raise KeyboardInterrupt('Owned evaluator shutdown')
    signal.signal(signal.SIGTERM,shutdown)
    source_path()
    case=read(os.environ['ROBOT_EVAL_CASE_FILE'])
    verify_case(case)
    from hybrid_rollout.robodojo.robodojo_server import session as module
    # The public bridge omitted native main.py's zero-delay render settings.
    # Apply the benchmark helper before AppLauncher, identically for all cases.
    from isaaclab.app import AppLauncher
    from env.camera_manager.capture.render_sync import add_zero_delay_kit_args
    original_launcher_init = AppLauncher.__init__
    def synced_launcher_init(self, args, *extra, **kwargs):
        add_zero_delay_kit_args(args)
        return original_launcher_init(self, args, *extra, **kwargs)
    AppLauncher.__init__ = synced_launcher_init
    Original=module.RoboDojoSession

    class MeasuredSession(Original):
        def __init__(self, env, output, task, evaluation_identity=None):
            identity={k:case[k] for k in ('case_id','layout_id','layout_sha256','eval_seed','task','variant')}
            resolved=Path(env.seed_manager.seed_info[case['layout_id']]['scene_layout'])
            if resolved.resolve()!=Path(case['layout_path']).resolve():
                raise ValueError('Native layout index differs from requested case')
            super().__init__(env,output,task,evaluation_identity=identity)
            # AppLauncher installs an immediate app.close signal handler. Restore
            # graceful Python unwinding so native evidence is saved first.
            signal.signal(signal.SIGTERM,shutdown)
            signal.signal(signal.SIGINT,shutdown)
            self.metrics=dict(reset_s=0., observation_record_s=0., control_execution_collection_s=0.,
                              policy_simulated_s=0., policy_physics_steps=0, actions=0)
            self.active=False
            self.started=None
            self.ended=None
            self.native_step=env.step
            def measured_step(*args,**kwargs):
                result=self.native_step(*args,**kwargs)
                if self.active:
                    decimation=kwargs.get('decimation',args[1] if len(args)>1 else 1)
                    self.metrics['policy_physics_steps']+=int(decimation)
                    self.metrics['policy_simulated_s']+=float(env.dt)*int(decimation)
                return result
            env.step=measured_step
            take=env.take_action
            def measured_take(*args,**kwargs):
                before=time.perf_counter()
                try:return take(*args,**kwargs)
                finally:
                    # Capture actual terminal action completion before image,
                    # video, summary and controller cleanup work. perf_counter
                    # uses the same host monotonic clock as the parent runner.
                    if self.active and bool(env.end_flag[0]) and 'native_terminal_monotonic' not in self.metrics:
                        self.metrics['native_terminal_monotonic']=time.perf_counter()
                    self.metrics['control_execution_collection_s']+=time.perf_counter()-before
                    self.metrics['actions']+=1
            env.take_action=measured_take

        def _observe(self,*args,**kwargs):
            before=time.perf_counter()
            try:return super()._observe(*args,**kwargs)
            finally:self.metrics['observation_record_s']+=time.perf_counter()-before

        def reset(self,*args,**kwargs):
            import faulthandler
            before=time.perf_counter()
            # Persist diagnostics for cold-start/reset stalls; no scene data.
            with (self.output/'reset_stack_trace.log').open('w') as stack:
                faulthandler.dump_traceback_later(90,repeat=True,file=stack)
                try:
                    return super().reset(*args,**kwargs)
                finally:
                    faulthandler.cancel_dump_traceback_later()
                    self.metrics['reset_s']+=time.perf_counter()-before
                    self.started=time.perf_counter(); self.active=True
                    self.initial_observation_s=self.metrics['observation_record_s']
                    signal.signal(signal.SIGTERM,shutdown)
                    signal.signal(signal.SIGINT,shutdown)

        def _write_summary(self,reason):
            if self.episode_id is None:return
            before=time.perf_counter()
            if self.ended is None:self.ended=before
            self.metrics['episode_active_wall_s']=self.ended-self.started if self.started else None
            self.metrics['initial_observation_s']=getattr(self,'initial_observation_s',0.)
            self.metrics['active_observation_record_s']=self.metrics['observation_record_s']-getattr(self,'initial_observation_s',0.)
            super()._write_summary(reason)
            self.metrics['summary_finalization_s']=time.perf_counter()-before
            write(self.output/'timing.json',self.metrics)

        def dispatch(self,op,args):
            before=time.perf_counter()
            try:
                if op.startswith('public_'):
                    self._check_identity(args['episode_id'],args['step_id'])
                    import numpy as np
                    if op=='public_observation':
                        raw=self.env.get_obs()
                        states={f'{a}_{f}' for a in ('left','right') for f in
                                ('arm_joint_state','ee_joint_state','ee_pose')}
                        fields=('color','depth','distance_to_image_plane','intrinsic_matrix','extrinsic_matrix','shape')
                        vision={('cam_head' if n=='cam_high' else n):{k:v for k,v in c.items() if k in fields}
                                for n,c in raw['vision'].items() if n in ('cam_high','cam_head','cam_left_wrist','cam_right_wrist')}
                        return dict(instruction=raw['instruction'],state={k:v for k,v in raw['state'].items() if k in states},
                                    vision=vision,step=self.step_id,step_limit=self.metadata['max_episode_steps'])
                    if op=='public_position_ik':
                        from robots.robodojo.agent_support import _solve_ik_position
                        from types import SimpleNamespace
                        facade=SimpleNamespace(robot_manager=self.env.robot_manager,get_obs=lambda env_idx=0:self.env.get_obs())
                        return _solve_ik_position(facade,args['arm'],args['xyz'])
                    if op=='public_pose_ik':
                        robot=self.kinematics.robots[args['arm']]
                        return self.env.robot_manager.solve_ik(target_pose=args['pose'],env_idx=0,robot=robot)
                    if op=='public_native_step':
                        command=args['command']; row=self.obs['states'].copy()
                        for arm,offset in (('left',0),('right',7)):
                            if f'{arm}_arm_joint_state' in command:
                                row[offset:offset+6]=command[f'{arm}_arm_joint_state']
                            elif f'{arm}_ee_pose' in command:
                                result=self.env.robot_manager.solve_ik(target_pose=command[f'{arm}_ee_pose'],
                                    env_idx=0,robot=self.kinematics.robots[arm])
                                if result.get('status')!='Success':
                                    return dict(error='Native CuRobo IK did not find a solution',step_id=self.step_id,steps=[])
                                row[offset:offset+6]=result['joint_value']
                            if f'{arm}_ee_joint_state' in command:row[offset+6]=command[f'{arm}_ee_joint_state'][0]
                        return self.chunk_step(np.asarray([row]),adapter='public_native_step')
                    raise ValueError('Unsupported public operation: '+op)
                return super().dispatch(op,args)
            finally:
                with (self.output/'rpc_timing.jsonl').open('a') as stream:
                    stream.write(json.dumps(dict(op=op,start_monotonic=before,
                        elapsed_s=time.perf_counter()-before,step_id=self.step_id))+'\n')

    module.RoboDojoSession=MeasuredSession
    from hybrid_rollout.robodojo.robodojo_server import rpc
    receive=rpc.receive_packet
    def diagnosed_receive(connection):
        connection.settimeout(float(os.environ.get('ROBOT_EVAL_NATIVE_IDLE_TIMEOUT_S','900')))
        signal.signal(signal.SIGTERM,shutdown)
        signal.signal(signal.SIGINT,shutdown)
        directory=Path(sys.argv[sys.argv.index('--output')+1])
        with (directory/'rpc_receive_trace.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(event='receive_wait',time_monotonic=time.perf_counter(),timeout_s=connection.gettimeout()))+'\n')
        try:
            request=receive(connection)
            with (directory/'rpc_receive_trace.jsonl').open('a') as stream:
                stream.write(json.dumps(dict(event='received',op=request.get('op'),request_id=request.get('request_id'),time_monotonic=time.perf_counter()))+'\n')
            return request
        except BaseException as error:
            write(Path(sys.argv[sys.argv.index('--output')+1])/'rpc_receive_error.json',
                dict(error_type=type(error).__name__,error=str(error)))
            raise
    rpc.receive_packet=diagnosed_receive
    if os.environ.get('ROBOT_EVAL_NATIVE_IK')=='1' or os.environ.get('ROBOT_EVAL_PUBLIC_RGBD')=='1':
        from src.eval_client import eval_env
        create=eval_env.create_eval_env
        def with_native_ik(cfg,app):
            if os.environ.get('ROBOT_EVAL_NATIVE_IK')=='1':
                for robot in cfg.robot.robots:robot.need_planner=True
            if os.environ.get('ROBOT_EVAL_PUBLIC_RGBD')=='1':enable_public_rgbd(cfg)
            return create(cfg,app)
        eval_env.create_eval_env=with_native_ik
    from hybrid_rollout.robodojo.robodojo_server.server import main as run
    run()


if __name__=='__main__':main()
