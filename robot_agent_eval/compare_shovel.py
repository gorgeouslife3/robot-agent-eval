"""Build the single-scene comparison from recorded attempts, without API/GPU use."""
from collections import Counter
import json
from pathlib import Path

from .common import ROOT, read, write

CASE_ID = 'general_pickup:seed0:layout1'


def describe_run(path):
    result, launch = read(path/'result.json'), read(path/'launch.json')
    calls = [json.loads(line) for line in (path/'model_requests.jsonl').read_text().splitlines()] if (path/'model_requests.jsonl').exists() else []
    history = read(path/'controller/history.json') if (path/'controller/history.json').exists() else []
    trace = [json.loads(line) for line in (path/'controller/react_trace.jsonl').read_text().splitlines()] if (path/'controller/react_trace.jsonl').exists() else []
    by_sequence = {r['sequence']-1:r for r in trace if r['event']=='executed'}
    request_metrics=[]
    for call in calls:
        request_metrics.append({k:call.get(k) for k in ('call','started_monotonic','elapsed_s','status',
                                                      'usage','error','error_type','http_status')})
    phase_metrics={}
    for file in sorted((path/'controller').glob('model_output_*.json')):
        model_output=read(file)
        for item in model_output.get('output',[]):
            if item.get('type')!='function_call' or item.get('name')!='robot_action':continue
            args=json.loads(item['arguments']);stage=args.get('stage','unknown')
            entry=phase_metrics.setdefault(stage,dict(model_requests=0,model_wait_s=0.,input_tokens=0,output_tokens=0))
            entry['model_requests']+=1;entry['model_wait_s']+=model_output['elapsed_s']
            entry['input_tokens']+=model_output['usage']['input_tokens']
            entry['output_tokens']+=model_output['usage']['output_tokens']
    sequence=[]
    for item in history:
        response=item.get('response',{})
        extra=by_sequence.get(item['decision'],{})
        sequence.append(dict(sequence=item['decision']+1,start_step=item['start_tick'],end_step=item['end_tick'],
            stage=extra.get('stage'),mode=response.get('mode'),source=item.get('source'),
            reason=response.get('reason'),target=response.get('target'),
            arm=extra.get('arm'),translation_m=extra.get('translation_m'),
            rotation_xyz_deg=extra.get('rotation_xyz_deg'),gripper=extra.get('gripper'),
            expected_effect=extra.get('expected_effect'),next_check=extra.get('next_check'),
            native_terminal=item.get('terminal'),native_success=item.get('native_success')))
    return dict(run=str(path),result=result,condition=launch.get('method_condition'),
        frozen_layout_sha256=launch['case']['layout_sha256'],
        model=launch['model_config']['model'],reasoning_effort=launch['model_config']['reasoning_effort'],
        budgets={k:launch['model_config'][k] for k in ('max_decisions','max_model_calls_per_episode',
                     'max_total_tokens_per_episode','max_episode_wall_s')},
        harness=launch.get('harness'),model_usage_scope='Whole attempt; may include requests after native termination',
        recorded_total_tokens=result['model_input_tokens']+result['model_output_tokens'],
        recorded_uncached_input_tokens=result['model_input_tokens']-result.get('model_cached_input_tokens',0),
        recorded_reasoning_output_tokens=sum(((c.get('usage') or {}).get('output_tokens_details') or {}).get('reasoning_tokens',0) for c in calls),
        executed_decisions=len(history),rejected_actions=sum(e['event']=='rejected' for e in trace),
        control_sources=dict(Counter(i.get('source') for i in history)),sequence=sequence,
        request_metrics=request_metrics,model_phase_metrics=phase_metrics)


def fmt(value):
    if value is None:return '—'
    if isinstance(value,float):return f'{value:.2f}'
    return str(value)


def main():
    rows=[]
    for p in sorted((ROOT/'runs').glob('*/result.json')):
        result=read(p)
        if result.get('case_id')==CASE_ID and result['method'] in ('astra_direct','astra_hybrid','astra_react_skill'):
            rows.append(describe_run(p.parent))
    eligible={method:[r for r in rows if r['result']['method']==method and r['result']['task_result_eligible']]
              for method in ('astra_react_skill','astra_direct')}
    findings=[]
    # A single eligible attempt in each condition permits this pilot illustration.
    # With retries, retain every row and do not silently select a successful one.
    if all(len(attempts)==1 and attempts[0]['result']['success_within_budget'] for attempts in eligible.values()):
        new=eligible['astra_react_skill'][0];old=eligible['astra_direct'][0]
        newtime=new['result']['timing']['episode_active_wall_s'];oldtime=old['result']['timing']['episode_active_wall_s']
        findings=[f'本次新harness原生成功，用时{newtime:.2f}秒，比历史Direct成功尝试短{(1-newtime/oldtime)*100:.1f}%。',
                  f'实际控制步数从{old["result"]["native_steps"]}增到{new["result"]["native_steps"]}；执行路径并没有更短。',
                  f'记录总token从{old["recorded_total_tokens"]:,}降到{new["recorded_total_tokens"]:,}，下降{(1-new["recorded_total_tokens"]/old["recorded_total_tokens"])*100:.1f}%，其中旧版大量输入来自缓存。',
                  f'不含缓存的输入token从{old["recorded_uncached_input_tokens"]:,}到{new["recorded_uncached_input_tokens"]:,}；输出token从{old["result"]["model_output_tokens"]:,}到{new["result"]["model_output_tokens"]:,}，不能把总token下降直接解释为费用同比下降。']
    ready=[]
    for method in ('rpent_astra','gap_astra','phyagentos_official_astra','phyagentos_custom_astra'):
        attempts=[read(p) | {'run':str(p.parent)} for p in sorted((ROOT/'runs').glob('*/result.json'))
                  if read(p).get('case_id')==CASE_ID and read(p).get('method')==method]
        ready.append(dict(method=method,status='local_adapter_trials_recorded' if attempts else 'pending',
                          attempts=attempts,report=str(ROOT/'results/shovel-framework-comparison/report.zh-CN.md')))
    output=ROOT/'results/shovel-harness-comparison'
    output.mkdir(parents=True,exist_ok=True)
    write(output/'comparison.json',dict(case_id=CASE_ID,attempts=rows,framework_readiness=ready,findings=findings,
        caveats=['Existing scene was used to design the skill: this is a development demonstration, not held-out generalization.',
                 'Historical Direct/Hybrid and new ReAct have different scaffolds/output caps and run dates; not an isolated skill-effect experiment.',
                 'One layout/attempt does not estimate success rate; retain every retry and all resource failures.']))
    lines=['# 铲子场景：初版 ReAct skill 对照','',f'冻结案例：`{CASE_ID}`。本报告由已保存记录生成，不启动模型或仿真。','',f'后续 RPent、GaP、PhyAgentOS 的本机试跑及完整输入审计见[框架比较报告]({ROOT}/results/shovel-framework-comparison/report.zh-CN.md)。此处保留最初三种控制条件的详细对照。','']
    lines.extend('- '+finding for finding in findings)
    lines+=['',
        '新方法改变了两项因素：缩短控制循环上下文，以及增加任务 skill。它与原版的时间差不能全部归因于skill；要单独验证skill效果，需在同一新harness中比较启用与禁用skill。','',
        '此铲子布局已被用于设计skill，属于开发演示。后续应选择未参与设计的铲子布局验证，不把这次成绩作为泛化成功率。','',
        '| 方法/尝试 | 原生结果 | 状态 | 任务现实时间(s) | 控制步 | 模型请求 | 输入token | 缓存输入token | 输出token | 合计token |','|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        r=row['result'];native='成功' if r['native_complete'] and r['native_success'] else '失败' if r['native_complete'] else '未完成/未知'
        lines.append(f'| [{r["method"]}]({row["run"]}/result.json) | {native} | {r["status"]} | {fmt(r["timing"].get("episode_active_wall_s"))} | {r["native_steps"]} | {r["model_requests"]} | {r["model_input_tokens"]} | {r.get("model_cached_input_tokens",0)} | {r["model_output_tokens"]} | {row["recorded_total_tokens"]} |')
    lines+=['',
            '任务时间从环境重置后到原生结束或预算停止；服务启动和重置另有记录。token统计覆盖整次尝试，可能含原生成功后的整理请求；缓存输入包含在总输入内，不能再加一次。输出包含服务计入的推理token。缺少用量的请求不能当0费用；价格未知，不推算金额。','',
            '## 方法在这个场景里怎样分工','',
            '| 方法 | 谁选择动作与顺序 | 如何定位/执行 |','|---|---|---|',
            '| 原版 Astra Direct | 持续Codex上下文，读图、计算、写笔记，自己选择每段动作 | RGB判断目标，给手部绝对目标；机器人运动学转关节控制 |',
            '| Astra Hybrid | Astra检查控制模型提议；接受或短暂接管 | pi0.5提出动作，Astra用RGB与机器人运动轨迹检查；接管用同一EEF桥接 |',
            '| 初版 ReAct skill | 短观察包+任务步骤与恢复建议；每轮一个动作调用 | RGB判断目标，输出相对移动和小角度旋转；同一EEF桥接，自动获取下一轮图像 |',
            '| RPent（代码结构） | planner选择分割、定位、运动或VLA工具，记录观察与记忆 | SAM3+深度定位，运动工具或pi0.5；这条路径有额外感知输入 |',
            '| GaP（代码结构） | 生成执行图，然后沿分支/循环执行工具 | 图中感知、抓取和移动技能；已新增本机RoboDojo双臂连接器，实际尝试见框架报告 |','',
            '## 逐次动作顺序与做法','',
            '以下是模型公开动作依据和实际执行回执。stage是模型的进度标签，不是评测器证明完成的阶段；实际成败由环境判定。完整坐标、夹爪、期望效果和下一项检查保存在comparison.json及每次运行的controller文件中。']
    for row in rows:
        path=Path(row['run']);r=row['result']
        lines+=['',f'### {path.name}','',
                f'模型：{row["model"]}；推理设置：{row["reasoning_effort"]}；实际动作决策：{row["executed_decisions"]}；拒绝动作：{row["rejected_actions"]}。',
                '', '| 顺序 | 控制步区间 | 来源/阶段 | 公开动作依据 |','|---:|---|---|---|']
        for action in row['sequence']:
            reason=(action.get('reason') or '').replace('|','\\|').replace('\n',' ')
            lines.append(f'| {action["sequence"]} | {action["start_step"]} → {action["end_step"]} | {action.get("stage") or action.get("source") or action.get("mode")} | {reason} |')
        if not row['sequence']:lines+=['', '本次没有执行机械臂动作。']
        if row['model_phase_metrics']:
            lines+=['','模型所选阶段的请求开销（阶段标签不等于环境验证完成）：','',
                    '| 阶段 | 请求数 | 模型等待(s) | 输入token | 输出token |','|---|---:|---:|---:|---:|']
            for stage,metric in row['model_phase_metrics'].items():
                lines.append(f'| {stage} | {metric["model_requests"]} | {metric["model_wait_s"]:.2f} | {metric["input_tokens"]} | {metric["output_tokens"]} |')
    lines+=['','## 后续框架实测','']
    for item in ready:
        lines.append(f'- {item["method"]}：已记录 {len(item["attempts"])} 次尝试；[详细输入、工具顺序与结果]({item["report"]})。')
    write(output/'framework-readiness.json',dict(check='Local adapter attempts; source-only registration audit remains historical',conditions=ready))
    lines+=['', '保留全部部署故障与方法失败；完整官方复现与本机移植条件不同，详见框架报告。','']
    (output/'report.zh-CN.md').write_text('\n'.join(lines))
    print(output/'report.zh-CN.md')


if __name__=='__main__':main()
