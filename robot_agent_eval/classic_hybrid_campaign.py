"""Serial, resumable paired development/screening campaign with live reports."""
import argparse
from collections import Counter
from datetime import datetime
import fcntl
import json
import os
import shutil
from pathlib import Path
import traceback
import time
import numpy as np
from .common import ROOT, read, write, sha
from .runner import run_case

ARMS = ('vla', 'graspnet', 'vla_graspnet')


def now():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()


def diagnostics(run):
    proposals = [read(p).get('grasp_proposal', {}) for p in sorted((run/'controller/proposals').glob('*/proposal.json'))]
    history = read(run/'controller/history.json') if (run/'controller/history.json').exists() else []
    counts = Counter(p.get('status') for p in proposals)
    model_calls=[json.loads(line) for line in (run/'model_requests.jsonl').read_text().splitlines()] if (run/'model_requests.jsonl').exists() else []
    return dict(proposal_status_counts=dict(counts),
        model_service_failed_calls=sum(c.get('status')=='failed' or bool(c.get('error_type')) for c in model_calls),
        learned_candidate_count=sum(len(p.get('candidates', [])) for p in proposals),
        learned_inference_wall_s=sum(p.get('elapsed_s', 0) for p in proposals),
        decisions=len(history), decision_modes=dict(Counter(h['response']['mode'] for h in history)),
        decision_reasons=[dict(start_tick=h['start_tick'],end_tick=h['end_tick'],
                              mode=h['response']['mode'],reason=h['response']['reason']) for h in history])


def report(output, state):
    records = state.get('records', [])
    aggregate = []
    lines = ['# Astra 操作后端配对对比', '', f"更新时间：{now()}。状态：{state['status']}。",
        '', f"已结束 {len(records)} / {len(state['schedule'])} 次；当前：{state.get('current') or '无'}。",
        '', '按文档的全部 10 配置运行。先 30 个开发案例 × 3 条件，再 100 个测试案例 × 3 条件 × 2 遍，共 690 次。',
        '开发和测试分开；已有铲子开发结果不并入。AnyGrasp 按用户要求暂缓。',
        '', '共同条件：gpt-6-astra/xhigh、三相机 RGB、相同头部原始深度/标定、1200 秒控制墙钟、60 请求、200 万 token、60 决策；每任务原生步数上限保持原值。',
        'VLA 使用原 π0.5 和失败/意图接管门；GraspNet-only 无 VLA，Astra 可直接规划 bounded EEF；组合组保留原门并增加真实候选。',
        '这是完整架构比较：VLA 可以每决策执行 15 步，EEF 为 5 步，观测/模型成本及门控不同，不能归因成单个网络的纯质量差。',
        'GraspNet 指已固定第三方 PyTorch Contact-GraspNet，不代表所有 GraspNet 实现。抓取候选不提供推、插、放或双臂协调轨迹；这些阶段由 Astra 规划。',
        'SAM 使用实时 Astra 的文本或当前帧像素提示，统一阈值 .2；分割失败和候选空集均保留，不降低阈值、不回放语义种子。',
        '', '| 分组 | 配置 | 条件 | 已结束 | 预算内成功 | 原生成功/失败/未知 | 基础设施错误 | 控制均时秒 | 请求均数 |',
        '|---|---|---|---:|---:|---|---:|---:|---:|']
    tasks = [t['task'] for t in read(ROOT/'experiments/classic-comparison/suite.json')['tasks']]
    for split in ('development', 'test'):
        for task in tasks:
            for arm in ARMS:
                rows = [r for r in records if r['split'] == split and r['task'] == task and r['arm'] == arm]
                if not rows: continue
                native_success = sum(r['result'].get('native_success') is True for r in rows)
                native_failure = sum(r['result'].get('native_complete') and r['result'].get('native_success') is False for r in rows)
                infra = sum(not r['result']['task_result_eligible'] for r in rows)
                wins = sum(r['result']['success_within_budget'] is True for r in rows)
                elapsed = [r['result']['process']['controller_wall_s'] for r in rows if r['result']['process']['controller_wall_s'] is not None]
                requests = [r['result']['model_requests'] for r in rows]
                item = dict(split=split,task=task,arm=arm,n=len(rows),budget_success=wins,
                    native_success=native_success,native_failure=native_failure,
                    native_unknown=len(rows)-native_success-native_failure,infra_errors=infra,
                    mean_controller_s=float(np.mean(elapsed)) if elapsed else None,
                    mean_requests=float(np.mean(requests)))
                aggregate.append(item)
                seconds = f"{item['mean_controller_s']:.1f}" if elapsed else '—'
                lines.append(f"| {split} | {task} | {arm} | {len(rows)} | {wins} | {native_success}/{native_failure}/{item['native_unknown']} | {infra} | {seconds} | {item['mean_requests']:.1f} |")
    pairs = []
    rng = np.random.default_rng(0)
    for first, second in (('vla','graspnet'), ('vla','vla_graspnet'), ('graspnet','vla_graspnet')):
        by_case = {}
        for row in records:
            if row['split'] != 'test' or not row['result']['task_result_eligible'] or row['result']['success_within_budget'] is None: continue
            by_case.setdefault((row['case_id'],row['repeat']), {})[row['arm']] = row
        differences = {}
        for (case_id, repeat), arms in by_case.items():
            if first in arms and second in arms:
                differences.setdefault(case_id, []).append(int(arms[second]['result']['success_within_budget'])-int(arms[first]['result']['success_within_budget']))
        if differences:
            values = np.array([np.mean(v) for v in differences.values()])
            boot = np.mean(rng.choice(values,size=(2000,len(values)),replace=True),axis=1)
            pairs.append(dict(first=first,second=second,paired_cases=len(values),
                delta=float(values.mean()),case_bootstrap_ci95=np.quantile(boot,[.025,.975]).tolist()))
    lines += ['', '原生未知保持未知；预算停止单列为预算内未成功。基础设施错误不当作任务能力失败；检查逐次日志后判断可比性。配对差值仅使用两组均具有效任务记录的相同测试案例/遍次，按案例合并重复后 bootstrap；小样本区间仅供参考。',
              '服务失败请求也消耗共同预算；各次失败请求数另记，服务异常期间的预算结果体现运行可靠性，不能解释成后端任务能力。',
              '', '候选生成、候选空集、分割失败、EEF/VLA 步数与逐次公开决策理由保存在 summary.json / records.jsonl 和 run 原始文件；公开理由属于模型自述，不证明因果。',
              '', '## 优劣的评估边界', '',
              '- VLA：检验其在推、长流程、双臂配合中的轨迹与模型调用效率，同时检查抓偏、错误阶段及接管需求。',
              '- GraspNet-only：检验当前点云候选能否帮助抓取定位及姿态；同时量化后续运动、放置、插入、回臂需要 Astra 规划的成本。',
              '- 组合：检验候选能否改善 VLA 的抓取失败，并测量加载、分割、推理和门控带来的额外成本。',
              '', '以上是预注册评估问题；只有实际配对数据足够后才给任务适用性结论。全任务等权平均只在任务覆盖完整时报告。']
    for pair in pairs:
        lines.append(f"\n测试配对 {pair['second']} − {pair['first']}：{pair['delta']:.1%}（{pair['paired_cases']} 案例，案例 bootstrap 95% 区间 {pair['case_bootstrap_ci95'][0]:.1%}～{pair['case_bootstrap_ci95'][1]:.1%}）。")
    if state.get('stop_reason'): lines += ['', '停止原因：'+state['stop_reason']]
    write(output/'summary.json',dict(updated_at=now(),status=state['status'],aggregate=aggregate,paired_comparisons=pairs,
        records=records,current=state.get('current'),stop_reason=state.get('stop_reason')))
    (output/'report.zh-CN.md').write_text('\n'.join(lines)+'\n')


def run(output, wait_for_pid=None):
    output.mkdir(parents=True, exist_ok=True)
    lock = (ROOT/'results/classic-hybrid-gpu.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state_path = output/'state.json'
    if state_path.exists():
        state = read(state_path)
    else:
        schedule = []
        for name, repeats in (('classic-development.json', 1), ('classic-test-screening.json', 2)):
            manifest = read(ROOT/'manifests'/name)
            for repeat in range(repeats):
                for index, case in enumerate(manifest['cases']):
                    offset=(index+repeat+1)%3
                    order = ARMS[offset:]+ARMS[:offset]
                    for arm in order:
                        schedule.append(dict(case=case,arm=arm,split=manifest['split'],repeat=repeat))
        frozen = {str(p):sha(p) for p in [*(ROOT/'robot_agent_eval').glob('*.py'),
            *(ROOT/'configs/classic-hybrid').glob('*.json'),ROOT/'manifests/classic-development.json',
            ROOT/'manifests/classic-test-screening.json',ROOT/'experiments/classic-comparison/suite.json']}
        state = dict(created_at=now(),schedule=schedule,records=[],frozen_files=frozen,status='running',pid=os.getpid())
        write(output/'plan.json',dict(created_at=state['created_at'],schedule=schedule,frozen_files=frozen))
    state.update(status='running',pid=os.getpid(),stop_reason=None)
    try:
        if wait_for_pid:
            state.update(status='waiting_for_preflight',current=f'等待校准进程 {wait_for_pid} 结束')
            write(state_path,state); report(output,state)
            while True:
                if (output/'STOP').exists(): raise RuntimeError('Operator STOP marker found')
                try: os.kill(wait_for_pid,0)
                except ProcessLookupError: break
                time.sleep(2)
            state.update(status='running',current=None)
        for index in range(len(state['records']), len(state['schedule'])):
            if any(sha(p)!=digest for p,digest in state['frozen_files'].items()):
                raise RuntimeError('Frozen adapter/config/manifest changed; refusing to mix implementations')
            if (output/'STOP').exists():
                raise RuntimeError('Operator STOP marker found')
            if shutil.disk_usage(ROOT).free < 20*1024**3:
                raise RuntimeError('Less than 20 GiB free for native recordings; stopped before starting another episode')
            item = state['schedule'][index]
            state['current'] = dict(index=index,case_id=item['case']['case_id'],arm=item['arm'],split=item['split'],repeat=item['repeat'],started_at=now())
            write(state_path,state); report(output,state)
            run_dir,result = run_case(item['case'],'astra_hybrid',ROOT/f"configs/classic-hybrid/{item['arm']}.json",item['split'])
            row = dict(index=index,case_id=item['case']['case_id'],task=item['case']['task'],arm=item['arm'],
                split=item['split'],repeat=item['repeat'],run=str(run_dir),result=result,diagnostics=diagnostics(run_dir))
            state['records'].append(row); state['current'] = None
            with (output/'records.jsonl').open('a') as stream: stream.write(json.dumps(row,ensure_ascii=False)+'\n')
            write(state_path,state); report(output,state)
            # Repeated deployment failures must not consume hundreds of model episodes.
            recent = state['records'][-3:]
            if len(recent)==3 and all(not r['result']['task_result_eligible'] or (
                r['result']['status']=='controller_error' and r['result']['native_steps']==0) for r in recent):
                raise RuntimeError('Three consecutive infrastructure/zero-step controller failures; inspect logs before resuming')
            if len(recent)==3 and all(not r['result']['native_complete'] and
                r['diagnostics']['model_service_failed_calls']>=3 for r in recent):
                raise RuntimeError('Three consecutive incomplete episodes each with at least three model-service failures; service must recover before efficacy testing')
        state['status'] = 'complete'
    except Exception as error:
        state.update(status='stopped',stop_reason=str(error),traceback=traceback.format_exc())
    finally:
        state['current'] = None
        write(state_path,state); report(output,state)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--wait-for-pid',type=int)
    args=parser.parse_args(); run(args.output.resolve(),args.wait_for_pid)


if __name__=='__main__': main()
