"""Generate a report only from this queued part-2 batch; no old aggregates."""
from collections import Counter
import numpy as np
from support import ROOT, OWNED, now, owned, read, write

RESULTS=OWNED/'results/part2'
GROUPS=('H11','S00','S10','S01','S11')


def journal(path):
    if not path.exists():return []
    import json
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def summarize_run(run):
    launch=read(run/'launch.json');process=read(run/'process.json')
    control=read(run/'controller/summary.json') if (run/'controller/summary.json').exists() else {}
    native=read(run/'sim/evaluation_outcome.json') if (run/'sim/evaluation_outcome.json').exists() else {}
    sim_timing=read(run/'sim/timing.json') if (run/'sim/timing.json').exists() else {}
    calls=journal(run/'model_requests.jsonl');starts=journal(run/'model_request_starts.jsonl')
    usage_complete=all(any(c.get('call')==s.get('call') and isinstance(c.get('usage'),dict) for c in calls) for s in starts)
    elapsed=control.get('episode_active_wall_s')
    if sim_timing.get('native_terminal_monotonic') is not None and control.get('activity_start_monotonic') is not None:
        terminal_s=sim_timing['native_terminal_monotonic']-control['activity_start_monotonic']
    else:terminal_s=elapsed
    native_success=native.get('native_success') if native.get('valid_for_success_rate') else None
    input_tokens=sum((c.get('usage') or {}).get('input_tokens',0) for c in calls)
    cached=sum(((c.get('usage') or {}).get('input_tokens_details') or {}).get('cached_tokens',0) for c in calls)
    output=sum((c.get('usage') or {}).get('output_tokens',0) for c in calls)
    submitted=len(starts)
    within=(native_success is True and terminal_s is not None and terminal_s<=1200 and
        submitted<=80 and input_tokens<=8000000 and control.get('stop_reason')=='native_terminal')
    inference_files=list((run/'controller/proposals').glob('*/identity.json'))
    trace=journal(run/'controller/execution_trace.jsonl')
    monitor=journal(run/'controller/monitor_trace.jsonl')
    reviews=journal(run/'controller/reviews.jsonl')
    events=journal(run/'controller/time_events.jsonl')
    # Detailed trace timing reconciliation is independent of aggregate state.
    categories=control.get('time_categories',{})
    stop_reason=control.get('stop_reason',process['status'])
    initial=read(run/'sim/initial_observation_fingerprint.json') if (run/'sim/initial_observation_fingerprint.json').exists() else None
    result=dict(group_id=launch['group_id'],repeat_id=launch['repeat_id'],layout_id=13,
        run=str(run),native_terminated=bool(native.get('complete')),native_success=native_success,
        success_within_budget=within,success_420s=within and terminal_s<=420,success_1200s=within,
        stop_reason=stop_reason,native_steps=native.get('native_control_steps',control.get('step_id',0)),
        episode_active_wall_s=elapsed,terminal_elapsed_s=terminal_s,
        penalized_completion_time_s=terminal_s if within else 1200.,
        process_wall_s=process['process_wall_s'],time_categories=categories,
        timing_residual_s=control.get('timing_residual_s'),api_submitted=submitted,api_completed=len(calls),
        input_tokens=input_tokens,cached_input_tokens=cached,uncached_input_tokens=input_tokens-cached,
        output_tokens=output,usage_complete=usage_complete,recorded_usage_is_lower_bound=not usage_complete,
        model_service_failed_calls=sum(bool(c.get('error_type')) or c.get('status') in ('failed','incomplete') for c in calls),
        model_wait_s=sum(c.get('elapsed_s',0) for c in calls),vla_inferences=len(inference_files),
        student_steps=sum(t['end_step']-t['start_step'] for t in trace if t['source']=='student'),
        edit_steps=sum(t['end_step']-t['start_step'] for t in trace if t['source']=='edit'),
        eef_steps=sum(t['end_step']-t['start_step'] for t in trace if t['source']=='eef'),
        review_count=len(reviews),review_reasons=dict(Counter(reason for r in reviews for reason in r['reasons'])),
        shadow_phase_events=sum(len(t['phase_events']) for t in monitor),
        shadow_anomaly_events=sum(len(t['anomaly_events']) for t in monitor),
        rejected_actions=control.get('rejected_actions',0),initialization_fingerprints=initial,
        setup_error=process.get('error'),model_identity=[c.get('model_returned') for c in calls if c.get('model_returned')],
        cost=None,implementation=launch['implementation'],config_sha256=launch['config_sha256'])
    return result


def mean(rows,key):
    values=[r[key] for r in rows if r.get(key) is not None]
    return float(np.mean(values)) if values else None


def display(value,digits=2):
    return '—' if value is None else f'{value:.{digits}f}'


def comparisons(records):
    by_repeat={}
    for record in records:
        by_repeat.setdefault(record['repeat_id'],{})[record['group_id']]=record['result']
    definitions={
        '审查间隔延长：S00−H11':{'S00':1,'H11':-1},
        '阶段触发平均效应':{'S10':.5,'S00':-.5,'S11':.5,'S01':-.5},
        '异常触发平均效应':{'S01':.5,'S00':-.5,'S11':.5,'S10':-.5},
        '阶段与异常交互':{'S11':1,'S10':-1,'S01':-1,'S00':1}}
    metrics=['success_within_budget','penalized_completion_time_s','episode_active_wall_s',
             'api_submitted','input_tokens','uncached_input_tokens','output_tokens','vla_inferences']
    result=[]
    for label,terms in definitions.items():
        pairs=[(repeat,groups) for repeat,groups in by_repeat.items() if all(g in groups for g in terms)]
        values={}
        for metric in metrics:
            per_repeat=[]
            for repeat,groups in pairs:
                if all(groups[g].get(metric) is not None for g in terms):
                    per_repeat.append(dict(repeat_id=repeat,delta=sum(weight*float(groups[g][metric]) for g,weight in terms.items())))
            values[metric]=dict(mean_delta=float(np.mean([r['delta'] for r in per_repeat])) if per_repeat else None,per_repeat=per_repeat)
        time_metrics={}
        for category in ('astra_blocked','vla_infer','monitor','action_ack','logging_ipc'):
            diffs=[sum(weight*groups[g]['time_categories'].get(category,0) for g,weight in terms.items())
                   for _,groups in pairs if all(groups[g]['episode_active_wall_s'] is not None for g in terms)]
            time_metrics[category]=float(np.mean(diffs)) if diffs else None
        residual_diffs=[sum(weight*groups[g]['timing_residual_s'] for g,weight in terms.items())
                        for _,groups in pairs if all(groups[g].get('timing_residual_s') is not None for g in terms)]
        time_metrics['residual']=float(np.mean(residual_diffs)) if residual_diffs else None
        result.append(dict(label=label,terms=terms,paired_repeats=len(pairs),metrics=values,time_category_deltas=time_metrics))
    return result


def generate(state):
    records=state['records'];aggregates=[]
    lines=['# Astra Hybrid：审查频率、阶段与异常触发快速验证','',
        f'更新时间：{now()}。状态：**{state["status"]}**。已结束 {len(records)} / 15 次。','',
        '最新执行要求：general_pickup 的 layout13，每种策略重复 3 次；只运行第二部分。第一部分、第三部分和 ReAct 未启动。',
        '此前 layout1、单遍 layout13、多布局等执行提议均未排队，当前只有此版本。',
        '这是单布局机制验证。三个重复是相同场景的运行波动，不是三个独立布局；不据此估计泛化成功率或证明成功率非劣。','',
        '## 执行状态','']
    if state['status']=='queued':
        lines.append(f'等待已有 GPU 批次进程 {state["wait_for_pid"]} 自然结束并确认 GPU 空闲。没有暂停或终止已有任务，目前没有本轮实验结果。')
    if state.get('current'):lines.append('当前执行：'+str(state['current']))
    if state.get('stop_reason'):lines.append('停止原因：'+state['stop_reason'])
    lines+=['','## 实际对照设置','',
        '| 组 | 周期审查上限 | 阶段触发 | 异常触发 |','|---|---:|---|---|',
        '| H11 | 15 步 | 关 | 关 |','| S00 | 45 步 | 关 | 关 |','| S10 | 45 步 | 开 | 关 |',
        '| S01 | 45 步 | 关 | 开 |','| S11 | 45 步 | 开 | 开 |','',
        '共同条件：gpt-6-astra/xhigh、同一有界上下文与铲子任务经验、H50 π0.5 每正常执行 15 步刷新、每 5 步公开观测 ACK，1200 秒活动墙钟、200 原生步、80 请求、800 万输入 token。初始 Astra 审查所有组都有；周期间隔从最近一次审查重新计数。',
        '同一 CPU 颜色跟踪/公开状态监控在五组都运行，摘要类型相同；关闭的阶段/异常仍记录影子事件。监控只提出候选，不输出运动，颜色匹配不证明身份，共动不证明抓稳。Astra仍通过RGB和失败/意图门决定是否修正。',
        '这是新增精简 Responses Hybrid 宿主的内部对照。历史 Codex 宿主的结果不进入本轮配对统计；新监控能力也不是原报告已有能力。','',
        '## 各组结果与波动','',
        '| 组 | 已结束 | 1200秒成功 | 420秒成功 | 原生成功/失败/未知 | 活动时间均值±样本SD(s) | 惩罚完成时间均值(s) | 请求均值 | 输入均值 | 输出均值 |',
        '|---|---:|---:|---:|---|---:|---:|---:|---:|---:|']
    for group in GROUPS:
        rows=[r['result'] for r in records if r['group_id']==group]
        elapsed=[r['episode_active_wall_s'] for r in rows if r['episode_active_wall_s'] is not None]
        item=dict(group_id=group,n=len(rows),successes=sum(r['success_within_budget'] for r in rows),
            successes_420s=sum(r['success_420s'] for r in rows),native_success=sum(r['native_success'] is True for r in rows),
            native_failure=sum(r['native_success'] is False for r in rows),native_unknown=sum(r['native_success'] is None for r in rows),
            mean_active_s=mean(rows,'episode_active_wall_s'),sample_sd_active_s=float(np.std(elapsed,ddof=1)) if len(elapsed)>1 else None,
            mean_penalized_s=mean(rows,'penalized_completion_time_s'),mean_calls=mean(rows,'api_submitted'),
            mean_input=mean(rows,'input_tokens'),mean_cached_input=mean(rows,'cached_input_tokens'),
            mean_uncached_input=mean(rows,'uncached_input_tokens'),mean_output=mean(rows,'output_tokens'),
            usage_complete=all(r['usage_complete'] for r in rows),
            resources_per_success={k:sum(r[k] for r in rows)/sum(r['success_within_budget'] for r in rows)
                if any(r['success_within_budget'] for r in rows) else None for k in ['input_tokens','output_tokens','api_submitted']})
        aggregates.append(item)
        lines.append(f'| {group} | {len(rows)} | {item["successes"]} | {item["successes_420s"]} | {item["native_success"]}/{item["native_failure"]}/{item["native_unknown"]} | {display(item["mean_active_s"])} ± {display(item["sample_sd_active_s"])} | {display(item["mean_penalized_s"])} | {display(item["mean_calls"])} | {display(item["mean_input"],0)} | {display(item["mean_output"],0)} |')
    paired=comparisons(records)
    lines+=['','## 同遍配对差异与因素分析','',
        '差值以表内定义为准：时间和资源负值表示减少，成功差正值表示改善。失败/未知不算成功，惩罚完成时间记 1200 秒，避免把快速失败当成提速。样本只有三个同布局重复，不报告泛化区间或显著性结论。',
        '', '| 对照 | 配对遍数 | 成功比例差 | 惩罚时间差(s) | 实际活动时间差(s) | 请求数差 | 输入差 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for pair in paired:
        m=pair['metrics'];value=lambda k:display(m[k]['mean_delta'])
        lines.append(f'| {pair["label"]} | {pair["paired_repeats"]} | {value("success_within_budget")} | {value("penalized_completion_time_s")} | {value("episode_active_wall_s")} | {value("api_submitted")} | {value("input_tokens")} |')
    lines+=['','### 时间账本','',
        '| 对照 | Astra阻塞差(s) | VLA推理差(s) | 监控差(s) | 动作ACK差(s) | 记录IPC差(s) | 残差(s) |','|---|---:|---:|---:|---:|---:|---:|']
    for pair in paired:
        t=pair['time_category_deltas']
        lines.append('| '+pair['label']+' | '+' | '.join(display(t[k]) for k in ['astra_blocked','vla_infer','monitor','action_ack','logging_ipc','residual'])+' |')
    token_decomposition=None
    baseline=[r['result'] for r in records if r['group_id']=='H11']
    longer=[r['result'] for r in records if r['group_id']=='S00']
    if baseline and longer and len(baseline)==len(longer) and all(r['usage_complete'] for r in baseline+longer):
        na=sum(r['api_submitted'] for r in baseline);nb=sum(r['api_submitted'] for r in longer)
        if na and nb:
            ia=sum(r['input_tokens'] for r in baseline);ib=sum(r['input_tokens'] for r in longer)
            ua=ia/na;ub=ib/nb
            token_decomposition=dict(total_input_delta=ib-ia,call_count_component=(nb-na)*(ua+ub)/2,
                                    per_call_input_component=(ub-ua)*(na+nb)/2)
            lines+=['','输入账本（S00−H11，累计已完成尝试）：总输入差 '+display(ib-ia,0)+
                ' token；按对称恒等式分解，调用数贡献 '+display(token_decomposition['call_count_component'],0)+
                ' token，每次输入长度贡献 '+display(token_decomposition['per_call_input_component'],0)+
                ' token。此为资源记账分解，不能当作两个独立因果效应。']
    lines+=['','### 如何判断提升来源','',
        '- S00 对 H11：若调用减少且等待下降，说明减少常规审查有资源收益；同时检查抓取失败是否更晚被发现。',
        '- S10/S11 对各自关闭阶段触发组：检查关键节点审查是否改善阶段推进，或额外调用使等待增加。',
        '- S01/S11 对各自关闭异常触发组：检查异常调用、恢复和错误持续时间；未知、颜色误跟踪和无效触发都可能增加开销。',
        '- 交互差值检查两种触发是否互补；同一事件合并为一次请求，因此不能简单相加两者调用成本。',
        '- 本轮固定上下文、skill、VLA权重和正常刷新频率，不能估计这些固定因素本身的净收益；修正导致的额外VLA推理属于监督后续成本。','',
        '## 全部尝试','',
        '| 遍 | 组 | 停止原因 | 原生成功 | 预算成功 | 步 | 活动秒 | 请求 | 输入/缓存/输出 | 复核原因 | 原始记录 |',
        '|---:|---|---|---|---|---:|---:|---:|---|---|---|']
    for record in records:
        r=record['result']
        lines.append(f'| {record["repeat_id"]} | {record["group_id"]} | {r["stop_reason"]} | {r["native_success"]} | {r["success_within_budget"]} | {r["native_steps"]} | {display(r["episode_active_wall_s"])} | {r["api_submitted"]} | {r["input_tokens"]}/{r["cached_input_tokens"]}/{r["output_tokens"]} | {r["review_reasons"]} | [result.json]({r["run"]}/result.json) |')
    lines+=['','## 限制与完整性','',
        '缓存输入已包含在输入总量中；非缓存输入单列在 summary.json。缺失用量保留完整性标记，汇总为已记录下限，不补造货币费用。模型推理token按服务输出口径记录。',
        'API/传输/初始化故障、原生失败、预算停止分别保留；外部故障区块的敏感性分析需看逐遍记录，不能仅替换失败者。',
        '轻量监控在旧 layout1 的公开初始图及合成状态序列上做离线链路检查，未用 layout13 调阈值。尚无两位独立审阅者，监控精度/召回与恢复成功率不填写未经测量的数值。完整RGB、影子事件、公开模型理由和前后状态留供审计。',
        '已有任务正常排队，本轮不会修改旧文档、结果或公共执行器。静态依赖哈希运行前/后核对；旧批次自身更新其动态状态和报告不算本轮写入。']
    if state['status']=='complete':
        lines+=['','## 本轮结论','']
        for pair in paired:
            m=pair['metrics']
            lines.append(f'{pair["label"]}：本场景三遍配对平均请求变化 {display(m["api_submitted"]["mean_delta"])} 次，实际活动时间变化 {display(m["episode_active_wall_s"]["mean_delta"])} 秒，惩罚完成时间变化 {display(m["penalized_completion_time_s"]["mean_delta"])} 秒。成败与具体触发记录须共同判断；这是本场景观察，不构成泛化或非劣结论。')
        lines.append('静态依赖变化：'+str(state.get('immutable_changes',[])))
    write(RESULTS/'summary.json',dict(updated_at=now(),status=state['status'],aggregate=aggregates,
        paired_comparisons=paired,records=records,scope='layout13 times 3 repeats times 5 part2 groups',
        current=state.get('current'),stop_reason=state.get('stop_reason'),input_decomposition=token_decomposition))
    path=owned(RESULTS/'report.zh-CN.md');path.write_text('\n'.join(lines)+'\n')


if __name__=='__main__':generate(read(RESULTS/'state.json'))
