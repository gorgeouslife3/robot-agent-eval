"""GaP graph compiler/executor with a dual-ARX RoboDojo connector."""
import asyncio
import json
import os
import shutil
import threading
import time
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from gap_core.types import Observation, Se3Pose, Vec3, make_pose
from gap_core.tools import ToolRegistry
from .common import ROOT,write,sha
from .framework_io import PublicEnv,ResponsesClient,responses_payload,chat_reply,append_trace,image_block


class RoboDojoConnector:
    """Expose public RGB-D and native CuRobo control in GaP's typed API."""
    def __init__(self,env):
        self.env=env;self.tool_registry=ToolRegistry()
        for name,fn in [('get_observation',self.get_observation),('get_ee_pose',self.get_ee_pose),
            ('get_gripper',self.get_gripper),('go_to_pose',self.go_to_pose),('go_to_pose_cartesian',self.go_to_pose),
            ('open_gripper',self.open_gripper),('close_gripper',self.close_gripper),
            ('describe_workspace',self.describe_workspace),('describe_gripper',self.describe_gripper),('grasp_frame',self.grasp_frame),('solve_ik',self.solve_ik)]:
            self.tool_registry.register_callable('robot.'+name,fn,summary=fn.__doc__ or name)
    def get_observation(self)->Observation:
        """Public RGB-D in OpenCV camera coordinates and both measured arm poses."""
        raw=self.env.get_obs();cameras=[]
        for name,c in raw['vision'].items():
            T=np.asarray(c['extrinsic_matrix'],float)@np.diag([1,-1,-1,1])
            q=Rotation.from_matrix(T[:3,:3]).as_quat()
            depth=c.get('distance_to_image_plane',c.get('depth'))
            cameras.append(dict(name=name,rgb=np.asarray(c['color'],np.uint8)[...,:3],depth=np.asarray(depth,np.float32).squeeze(),
                intrinsics=np.asarray(c['intrinsic_matrix']),pose=make_pose(T[:3,3],[q[3],*q[:3]])))
        arms=[]
        for a in ('left','right'):
            s=raw['state'];p=s[a+'_ee_pose'];R=Rotation.from_quat([*p[4:7],p[3]]).as_matrix()
            # Robot config gripper_bias=0.145 m along link6 X. Canonical
            # grasp frame: local Z approaches, local X closes the fingers.
            Rtcp=R@np.array([[0,0,1],[1,0,0],[0,1,0]])
            q=Rotation.from_matrix(Rtcp).as_quat()
            arms.append(dict(joint_state={'positions':np.asarray(s[a+'_arm_joint_state'])},
                gripper_fraction=float(np.asarray(s[a+'_ee_joint_state']).ravel()[0]),ee_pose=make_pose(np.asarray(p[:3])+R@np.array([.145,0,0]),[q[3],*q[:3]])))
        return dict(cameras=cameras,arms=arms)
    def get_ee_pose(self,arm_id:int=0)->dict:
        """Measured grasp-center pose, Z approach/X close; arm 0=left, 1=right."""
        return {'pose':self.get_observation()['arms'][arm_id]['ee_pose']}
    def get_gripper(self,arm_id:int=0)->dict:
        """Return normalized opening, 0 closed and 1 open."""
        return {'fraction':self.get_observation()['arms'][arm_id]['gripper_fraction']}
    def _link_pose(self,pose):
        xyz=np.asarray([pose['position'][k] for k in ('x','y','z')]);q=[pose['rotation'][k] for k in ('w','x','y','z')]
        Rtcp=Rotation.from_quat([*q[1:],q[0]]).as_matrix()
        R=Rtcp@np.array([[0,0,1],[1,0,0],[0,1,0]]).T
        qlink=Rotation.from_matrix(R).as_quat()
        return [*(xyz-R@np.array([.145,0,0])),qlink[3],*qlink[:3]]
    def solve_ik(self,pose:Se3Pose,arm_id:int=0)->dict:
        """Read-only native IK for canonical grasp-center pose; unreachable => joints null."""
        result=self.env.solve_pose(('left','right')[arm_id],self._link_pose(pose))
        return {'joint_config':{'positions':result['joint_value']} if result.get('status')=='Success' else None,'success':result.get('status')=='Success'}
    def go_to_pose(self,pose:Se3Pose,arm_id:int=0,max_steps:int=40)->dict:
        """Move grasp center to world pose (Z approach, X close), converting to native link6 IK. Hold the other arm; <=max_steps (default 40) at 25Hz, all counted in native 200."""
        a=('left','right')[arm_id];link=self._link_pose(pose);xyz=np.asarray(link[:3]);q=link[3:]
        start=self.env.tick
        for _ in range(min(200,max_steps)):
            obs=self.env.get_obs();cur=np.asarray(obs['state'][a+'_ee_pose']);err=np.linalg.norm(cur[:3]-xyz)
            angle=(Rotation.from_quat([*cur[4:7],cur[3]]).inv()*Rotation.from_quat([*q[1:],q[0]])).magnitude()
            if err<.01 and angle<.1:break
            ik=self.env.solve_pose(a,[*xyz,*q])
            if ik.get('status')!='Success':raise RuntimeError('Native CuRobo cannot reach graph target')
            joints=np.asarray(obs['state'][a+'_arm_joint_state']);target=np.asarray(ik['joint_value']);bounded=joints+np.clip(target-joints,-.08,.08)
            self.env.step({a+'_arm_joint_state':bounded.tolist()})
            if self.env.ended:break
        append_trace(self.env.output,dict(tool='robot.go_to_pose',arguments={'pose':pose,'arm_id':arm_id},start_step=start,end_step=self.env.tick))
        return {'pose':self.get_observation()['arms'][arm_id]['ee_pose']}
    def _grip(self,opening,settle_steps,arm_id):
        a=('left','right')[arm_id];start=self.env.tick
        for _ in range(settle_steps):
            if self.env.ended:break
            self.env.step({a+'_ee_joint_state':[opening]})
        append_trace(self.env.output,dict(tool='robot.set_gripper',opening=opening,start_step=start,end_step=self.env.tick))
        return self.get_gripper(arm_id)
    def open_gripper(self,settle_steps:int=40,arm_id:int=0)->dict:
        """Open selected gripper; settling consumes native control steps."""
        return self._grip(1.,settle_steps,arm_id)
    def close_gripper(self,settle_steps:int=60,arm_id:int=0)->dict:
        """Close selected gripper; settling consumes native control steps."""
        return self._grip(0.,settle_steps,arm_id)
    def describe_workspace(self)->dict:
        """Describe control budgets; surface height must be measured from public depth."""
        return dict(align_clearance_m=.08,control_frequency_hz=25,step_limit=200,num_arms=2)
    def describe_gripper(self,arm_id:int=0)->dict:
        """Canonical grasp-center frame Z approach/X close, derived from X5 robot_config gripper_bias and URDF joint7/8. go_to_pose applies full orientation and .145m link6-X offset internally."""
        return dict(approach_axis={'x':0.,'y':0.,'z':1.},close_axis={'x':1.,'y':0.,'z':0.},
            width_fit={'stated':False},finger={'stated':False},opening_convention='0_closed_1_open',link6_to_grasp_center_m=.145)
    def grasp_frame(self,approach:Vec3,close_heading_deg:float)->dict:
        """Compose hand orientation from world approach and jaw closing direction."""
        z=np.array([approach[k] for k in ('x','y','z')]);z/=np.linalg.norm(z)
        h=np.deg2rad(close_heading_deg);x=np.array([np.cos(h),np.sin(h),0.]);x-=np.dot(z,x)*z;x/=np.linalg.norm(x)
        q=Rotation.from_matrix(np.column_stack([x,np.cross(z,x),z])).as_quat()
        return {'rotation':dict(w=float(q[3]),x=float(q[0]),y=float(q[1]),z=float(q[2]))}


def run(args,config):
    from .gap_compat import fix_dispatch_name_collision
    fix_dispatch_name_collision()
    from gap import agent,execute
    from gap.agent.config import PipelineConfig,CompositionConfig
    from gap.agent.llm import LlmConfig
    from gap.agent import llm,multi_agent
    env=PublicEnv(args.sim_port,args.layout,args.output,'gap_astra');conn=RoboDojoConnector(env)
    model=ResponsesClient(config,args.output)
    model_lock=threading.Lock()
    def request(payload):
        with model_lock:return model.request(payload)
    async def post(cfg,body):
        r=await asyncio.to_thread(request,responses_payload(body['messages'],config,body.get('tools')))
        return chat_reply(r)
    llm._post_openai_chat=post  # transport only; source tool-loop and compiler remain intact
    max_tool_rounds=config.get('gap_max_tool_rounds',6)
    if max_tool_rounds!=6:
        original_complete_tools=llm.complete_with_tools
        async def complete_tools(cfg,**kwargs):
            kwargs['max_rounds']=max_tool_rounds
            return await original_complete_tools(cfg,**kwargs)
        llm.complete_with_tools=complete_tools
    original=multi_agent.load_codegen_registries
    def load_tool_module(skills,name,registry):
        info=skills.get(name)
        module=skills._import_module(info.bundle_dir/'tools.py',f'gap_skills.tools.{name}.tools')
        from gap_core.tools import _registry as registered
        for entry in [*registered._PENDING_TOOLS,*registered._DRAINED_TOOLS]:
            if entry['fn'].__module__!=module.__name__:continue
            registry._tools.pop(entry['name'],None)
            registry.register_callable(entry['name'],entry['fn'],summary=entry['summary'],tags=entry['tags'])
        return module
    def registries(*a,**kw):
        skills,tools=original(*a,**kw)
        contract_changes={}
        for info in skills.list_skills():
            allowed=info.meta.allowed_tools
            if 'robot.go_to_pose' in allowed or 'robot.go_to_pose_cartesian' in allowed:
                additions=[n for n in ('robot.solve_ik','robot.grasp_frame') if n not in allowed]
                if additions:
                    allowed.extend(additions);contract_changes[info.meta.name]=additions
        write(args.output/'connector_skill_contract.json',dict(
            rule='Expose connector read-only IK and frame construction alongside motion tools in skill codegen catalogs',
            added_tool_permissions=contract_changes,skill_documents_and_canonical_scripts_unchanged=True))
        # Keep bundle tool logic; map only its hosted provider to the same
        # accounted Astra and resolve official SAM3 to the verified local file.
        from sam3 import model_builder
        model_builder.download_ckpt_from_hf=lambda:str(ROOT/'checkpoints/sam3/sam3.pt')
        vlm=load_tool_module(skills,'vlm',tools)
        load_tool_module(skills,'sam3',tools)
        load_tool_module(skills,'geometry',tools)
        dino=load_tool_module(skills,'grounding-dino',tools)
        def vision(prompt,images,model_name):
            content=[dict(type='text',text=prompt)]+[image_block(im) for im in images]
            response=request(responses_payload([dict(role='user',content=content)],config))
            return chat_reply(response)['choices'][0]['message']['content'] or ''
        vlm._PROVIDERS={'astra':vision};os.environ['GAP_VLM_PROVIDER']='astra'
        os.environ['GAP_VLM_MODEL']=config['model']
        os.environ['GAP_DINO_MODEL']=str(ROOT/'checkpoints/grounding-dino-base')
        dino._MODEL_NAME=os.environ['GAP_DINO_MODEL']
        # The execution registry uses these exact source callables too. This
        # bypasses only their uv/stdio launch transport in the shared venv.
        for name in ('vlm','sam3','grounding-dino','geometry'):load_tool_module(skills,name,conn.tool_registry)
        tools._tools={n:d for n,d in tools._tools.items() if not n.startswith(('robot.','sim.'))}
        # New connector-owned descriptors replace only platform tool signatures.
        for name,d in conn.tool_registry.runtime_tools().items():
            tools._tools[name]=d
        return skills,tools
    multi_agent.load_codegen_registries=registries
    paths=ROOT/'source-snapshots/gap_skills'
    write(args.output/'text_provenance.json',dict(framework='GaP',skill_library=str(paths),prior_custom_shovel_skill=False,
        skill_inventory={str(p.relative_to(paths)):sha(p) for p in paths.rglob('SKILL.md')},
        system_sources=['gap/agent/prompts','gap/agent/prompt_assembler.py'],transport_adapter='Planner and VLM bundle providers mapped to the same accounted Astra Responses',sam3_available=(ROOT/'checkpoints/sam3/sam3.pt').exists(),
        gripper_geometry_sources=['RoboDojo/Assets/Robots/x5/robot_config.yml: gripper_bias=0.145','dual_arx_x5.urdf: joint7/8 close along link6 Y'],
        robot_context='Dual ARX X5, 200 control steps; no hidden object coordinates',checkpoint_condition='GaP semantic checkpoints unavailable without world_snapshot; native outcome evaluated externally',
        codegen_max_tool_rounds=max_tool_rounds,codegen_original_default_rounds=6,
        interface_fixes=['Dispatch target name positional-only; tool arguments preserved',
            'Motion-skill codegen catalogs expose connector solve_ik and grasp_frame; original documents/scripts unchanged']))
    prompt=env.observation['instruction']+'\nExecution platform: RoboDojo, dual ARX X5 (arm_id 0 left, 1 right), world-frame grasp-center poses (+Z approach, +X jaw close). The connector internally converts full orientation and the .145m link6-to-grasp-center offset. robot.solve_ik checks reachability without moving; robot.go_to_pose holds the other arm and permits max_steps (default 40). Control is 25Hz, total 200 steps including requested gripper settling; choose settle_steps within that total. Use public RGB-D; do not request simulator object truth. Lift the target; do not place it back. Use canonical scripts from the supplied skill library.'
    (args.output/'USER.md').write_text(prompt)
    cfg=PipelineConfig(task=prompt,skills=paths,llm=LlmConfig(model=config['model'],endpoint='loopback Responses adapter',temperature=None,max_tokens=16384,max_concurrent_requests=1),
        composition=CompositionConfig(max_codegen_regenerations=0))
    started=time.perf_counter()
    write(args.output/'adapter_ready.json',dict(method=args.method,connector_tools=list(conn.tool_registry.runtime_tools())))
    generation_completed=None
    try:
        if config.get('gap_reuse_graph'):
            origin=Path(config['gap_reuse_graph']).resolve()
            if not origin.is_relative_to(ROOT/'runs') or not (origin/'workflow.json').exists():
                raise ValueError('Reuse requires a previously recorded local generated workflow')
            graph_path=args.output/'generated_graph/task_00';shutil.copytree(origin,graph_path)
            registries(paths)
            write(args.output/'graph_reuse.json',dict(origin=str(origin),workflow_sha256=sha(origin/'workflow.json'),
                prior_generation_record=str(origin.parents[1]/'graph_generation.json'),
                condition='Reuse after tool-transport repair; prior generation cost remains separate, not free'))
        else:
            graph=agent.generate_sync(prompt,skills=paths,model=config['model'],config=cfg,out_dir=args.output/'generated_graph')
            graph_path=graph.path
        generation_completed=time.perf_counter()
        write(args.output/'graph_generation.json',dict(elapsed_s=time.perf_counter()-started,path=str(graph_path),reused=bool(config.get('gap_reuse_graph'))))
        start=time.perf_counter();result=execute(graph_path,conn,skills=paths,trace_dir=args.output/'graph_trace',checkpoints='off',max_node_workers=1)
        write(args.output/'graph_execution.json',dict(elapsed_s=time.perf_counter()-start,success=result.success,error=str(result.error),graph_path=str(graph_path),result=str(result)))
        if result.error:raise RuntimeError(str(result.error))
    finally:
        write(args.output/'graph_generation_attempt.json',dict(elapsed_s=(generation_completed or time.perf_counter())-started));env.close()
