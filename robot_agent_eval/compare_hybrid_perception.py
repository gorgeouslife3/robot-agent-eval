"""Audit true Astra hybrid task trials, including partial and failed attempts."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import numpy as np
from .common import ROOT,read,write


def digest_array(value):
    value=np.ascontiguousarray(value)
    return hashlib.sha256(str(value.dtype).encode()+str(value.shape).encode()+value.tobytes()).hexdigest()


def has_measurement(value):
    """Distinguish an attached measurement from a prompt mentioning its name."""
    if isinstance(value,dict):
        if isinstance(value.get('perception_evidence'),dict) and value['perception_evidence'].get('frame'):
            return True
        return any(has_measurement(v) for v in value.values())
    if isinstance(value,list):return any(has_measurement(v) for v in value)
    if isinstance(value,str) and 'perception_evidence' in value:
        # Codex may prefix a tool output with a truncation notice and follow
        # the JSON packet with separate image descriptors. Decode the packet
        # itself; a bare mention in common instructions must remain false.
        try:
            start=value.index('{')
            packet,_=json.JSONDecoder().raw_decode(value,start)
            return has_measurement(packet)
        except (ValueError,TypeError):return False
    return False


def collect(run):
    launch=read(run/'launch.json');result=read(run/'result.json')
    original_result=result
    if (run/'accounting_transport_revision.json').exists():
        result=read(run/'accounting_transport_revision.json')['result']
    if (run/'accounting_budget_revision.json').exists():
        result=read(run/'accounting_budget_revision.json')['result']
    controller=run/'controller'
    decisions=[dict(path=str(p),**read(p)) for p in sorted(controller.glob('response_*.json'))]
    frames=[dict(path=str(p),**read(p)) for p in sorted((controller/'perception_host').glob('*/evidence.json'))]
    evidence_inputs=[]
    for p in sorted((run/'model_inputs').glob('*.json')):
        if has_measurement(read(p)):evidence_inputs.append(str(p))
    hashes={}
    initial=controller/'perception_host/0000'
    if (initial/'public_rgbd.npz').exists():
        with np.load(initial/'public_rgbd.npz',allow_pickle=False) as data:
            hashes.update({key:digest_array(data[key]) for key in data.files})
        from PIL import Image
        hashes['rgb']=digest_array(np.asarray(Image.open(initial/'cam_head.png')))
    common_config={k:v for k,v in launch['model_config'].items() if k!='hybrid_perception'}
    worker=(controller/'perception_host/model_identity.json')
    rgb_alignment=[]
    for p in sorted((controller/'observations').glob('*/observation.json')):
        packet=read(p);step=packet['step_id']
        sensor=controller/'perception_host'/f'{step:04d}'/'cam_head.png'
        teacher=p.parent/'cam_high.png'
        if sensor.exists() and teacher.exists():
            from PIL import Image
            a=np.asarray(Image.open(sensor));b=np.asarray(Image.open(teacher))
            if a.shape==b.shape:
                difference=np.abs(a.astype(float)-b.astype(float))
                rgb_alignment.append(dict(step_id=step,exact_match=bool(np.array_equal(a,b)),
                    mean_absolute_channel_difference_0_255=float(difference.mean()),
                    max_absolute_channel_difference_0_255=float(difference.max())))
    calls=[json.loads(line) for line in (run/'model_requests.jsonl').read_text().splitlines()] if (run/'model_requests.jsonl').exists() else []
    failed_calls=[c for c in calls if c.get('status')=='failed' or c.get('error_type') or c.get('error')]
    retries=[]
    if (run/'controller.log').exists():
        for line in (run/'controller.log').read_text(errors='replace').splitlines():
            try:event=json.loads(line)
            except ValueError:continue
            if event.get('event')=='codex_transport_retry':retries.append(event)
    return dict(run=str(run),result=result,original_result=original_result,
        condition=launch['hybrid_perception']['mode'],decisions=decisions,
        decision_modes=dict(Counter(d['mode'] for d in decisions)),
        perception_frames=frames,model_inputs_with_evidence=evidence_inputs,initial_sensor_hashes=hashes,
        common_config_sha256=hashlib.sha256(json.dumps(common_config,sort_keys=True).encode()).hexdigest(),
        common_prompt_sha256=launch['perception_common_prompt_sha256'],
        implementation_sha256=result['implementation_sha256'],
        policy_identity=read(run/'policy_identity.json') if (run/'policy_identity.json').exists() else None,
        perception_identity=read(worker) if worker.exists() else None,
        failed_model_requests=failed_calls,model_transport_retries=retries,
        public_vs_teacher_rgb=rgb_alignment,
        failure=read(controller/'failure.json') if (controller/'failure.json').exists() else None,
        experimental_scope='Fresh Astra hybrid execution on previously developed shovel layout; no semantic replay, no generalization estimate')


def main():
    out=ROOT/'results/astra-hybrid-perception';out.mkdir(exist_ok=True)
    rows=[];running=[]
    for p in sorted((ROOT/'runs').glob('20261013-*/launch.json')):
        launch=read(p)
        if not launch.get('hybrid_perception'):continue
        if (p.parent/'result.json').exists():rows.append(collect(p.parent))
        else:running.append(dict(run=str(p.parent),condition=launch['hybrid_perception']['mode']))
    write(out/'attempts.json',rows)
    primary={}
    for row in rows:
        if row['result']['task_result_eligible']:primary[row['condition']]=row
    lines=['# Astra hybrid：新增感知与实际任务执行', '',
        '本轮所有任务动作仍由真实Astra hybrid决策：接受π0.5提议、edit或EEF接管。'
        '感知只提供观测，没有本地自主抓取序列，没有历史Astra语义种子回放。',
        '所有组使用同一开发铲子layout1，420秒控制进程预算。尚无放置、未见布局或实机评估。', '',
        '## 主要任务对照', '',
        '每个条件最近一次实际进入任务的尝试如下；基础设施中断与全部重试在下一表保留。'
        '本表每条件只列最近一次尝试，SAM+原始深度还有一次受上游错误影响的任务尝试；'
        '单布局重复有限，不能把这张表当成功率或因果收益。', '',
        '| 新增感知 | 实际执行步 | 420秒结果 |', '|---|---:|---|']
    labels=dict(none='H0 无新增感知',raw_depth='H1 原始深度',sam_raw_depth='H2 SAM3 + 原始深度',
        sam_lingbot_depth='H3 SAM3 + LingBot深度')
    for mode in ('none','raw_depth','sam_raw_depth','sam_lingbot_depth'):
        if mode not in primary:continue
        r=primary[mode]['result']
        description=('原生成功；预算时间按历史回执核验，见下文' if r['success_within_budget'] else
            '预算内成功时间未知' if r['success_within_budget'] is None else
            '预算内未完成' if not r['native_complete'] else '原生结束，未成功')
        if primary[mode]['failed_model_requests']:description+=f'；{len(primary[mode]["failed_model_requests"])}次模型请求失败'
        lines.append(f'| {labels[mode]} | {r["native_steps"]} | {description} |')
    lines += ['', '感知证据确实进入加感知组的Astra请求；本轮主要被用于确认目标侧，'
        '尚未证明精确几何改变了接近/抓取。速度瓶颈仍是Astra等待，单次H3成功不能归因于LingBot。', '',
        '## 逐次结果', '',
        '| 条件 | 原生控制步 | student/edit/eef决策数 | Astra提交/结束 | 已记录等待(s) | 控制进程含清理(s) | 状态 | 原生成功 | 严格420秒内成功 |',
        '|---|---:|---|---:|---:|---:|---|---|---|']
    for row in rows:
        r=row['result'];m=row['decision_modes'];process=r['process']
        lines.append(f'| [{row["condition"]}]({row["run"]}/result.json) | {r["native_steps"]} | '
            f'{m.get("student",0)}/{m.get("edit",0)}/{m.get("eef",0)} | '
            f'{r["model_requests"]}/{r["model_requests_finished"]} | {r["model_wait_s"]:.2f} | '
            f'{process.get("controller_wall_s") or 0:.2f} | {r["status"]} | {r["native_success"]} | '
            f'{r["success_within_budget"] if r["success_within_budget"] is not None else "未确认"} |')
    if running:lines += ['',f'正在运行、尚无最终结果：{running}。']
    lines += ['', '提交/结束不一致或失败请求没有usage时，用量不完整；未结束调用的等待仅是已记录下限。'
        '没有原生结束的预算耗尽任务算预算内未完成，原生分数保持未知。'
        '首个H0尝试仿真器异常退出（-11、RPC EOF），5步后中断，归基础设施而不是抓取失败；'
        '原result保留，另存accounting_transport_revision修正汇总分类。H0重试也发生仿真器异常退出；'
        '首个H1尚未启动controller时，campaign父进程工具会话以143结束，来源未知；'
        '两个已加载的子服务已清理，0请求/0控制步，不作为任务对照样本。', '',
        'SAM+LingBot达到独立原生终止成功（56步），随后保存最后RGB时被预算信号中断。'
        '最终action_000055.json已经记录terminated=true、success=true、step_id=56；'
        '其文件时间距controller命令文件写入419.493秒，后者先于controller启动。'
        '在主机时钟未跳变的条件下，这支持原生成功发生在420秒内，但余量不足1秒。'
        '这是历史文件时间的上界证据，不是精确单调时钟完成时间；不能用episode_active_wall_s=389.23秒替代。'
        '原结果不覆盖，另存accounting_budget_revision记录依据。', '',
        '首次SAM+原始深度组有2次上游模型响应失败；原Codex日志明确记录“Concurrency limit exceeded for user”。'
        '两次失败等待共61.24秒并触发自动重连，尽管本机GPU试验是串行。'
        '这会挤占420秒任务预算，不能把该次35步停滞解释为SAM使Astra变慢；'
        '失败请求计入总等待，但上游未给usage，计费用量不完整。', '',
        '## 感知证据是否进入Astra，以及Astra怎样决策', '']
    sam=primary.get('sam_raw_depth')
    if sam and sam['result'].get('terminal_controller_elapsed_upper_bound_s') is not None:
        value=sam['result']['terminal_controller_elapsed_upper_bound_s']
        at=lines.index('## 感知证据是否进入Astra，以及Astra怎样决策')
        lines[at:at]=[f'SAM+原始深度补跑达到原生成功（57步），终止动作文件时间给出的控制进程耗时上界为{value:.3f}秒；'
            '随后Astra收尾请求被420秒截止中断。该次没有已记录的失败响应，但末次请求用量未知。'
            '同样以accounting_budget_revision保存历史文件时间核验，不能把控制器超时等同于任务失败。', '',
            '首轮对照结束后，后续runner已补存controller启动单调时钟，native_server在终止动作后、'
            '保存观测前记录终止单调时钟；按同一截止计算预算成功。缺少时钟的历史截止成功须单独核验，'
            '汇总把未知预算结果单列，避免把收尾超时或超时后的完成混入成功率。'
            '该记账修复没有用于本批在线运行，不改变本批冻结实现身份。', '']
    for row in rows:
        lines += [f'### {Path(row["run"]).name} / {row["condition"]}', '',
            f'含perception_evidence的真实模型请求：{len(row["model_inputs_with_evidence"])}；'
            f'完成的本地感知观测：{len(row["perception_frames"])}。'
            f'[完整审计]({out}/attempts.json)。']
        lines.append(f'模型失败请求：{len(row["failed_model_requests"])}；记录的重连事件：{len(row["model_transport_retries"])}；'
            f'模型用量完整：{row["result"]["model_usage_complete"]}。')
        if row['perception_identity']:
            identity=row['perception_identity']
            lines.append(f'感知进程模型加载{identity["load_s"]:.2f}秒。')
        for d in row['decisions']:
            lines.append(f'- {Path(d["path"]).name}: {d["mode"]}, {d.get("steps",0)}步；公开理由：{d.get("reason","")}')
        for f in row['perception_frames']:
            objects=f['objects'];ref=f.get('depth_refinement') or {}
            lines.append(f'- 观测step={f["frame"]["step_id"]}：目标数{len(objects)}，'
                f'感知{f["elapsed_s"]:.3f}秒，LingBot前向{ref.get("inference_s","—")}；'
                f'错误={f["errors"]}。[回执]({f["path"]})。')
    lines += ['', '这里只审计公开assessment/reason与实际response，不读取私有推理。'
        '字段出现在请求中只是“可见”的证据；决策引用和动作变化才支持它被使用，仍不等于任务成功。', '',
        '## 共同条件检查', '']
    if rows:
        groups={k:len({r[k] for r in rows}) for k in ('common_config_sha256','common_prompt_sha256','implementation_sha256')}
        lines.append(f'全部尝试的共同配置/共同说明/实现身份种类数：{groups}。'
            '初次部署重试可能跨实现版本，不能将不同版本合并成功率；对照批次在campaign文件中单列。')
        campaign=ROOT/'results/hybrid-perception-campaign-20261013.json'
        if campaign.exists():
            paths={r['run'] for r in read(campaign)};batch=[r for r in rows if r['run'] in paths]
            groups={k:len({r[k] for r in batch}) for k in ('common_config_sha256','common_prompt_sha256','implementation_sha256')}
            lines.append(f'同一campaign已结束组的共同身份种类数：{groups}。')
        lines.append('π0.5仍只消费原RGB/任务/proprio；新增mask、深度和几何不会进入π0.5输入。'
            'H0与所有组均host采集原始RGB-D，H0的host原始深度对Astra禁止读取。')
        batch=list(primary.values())
        groups={k:len({r[k] for r in batch}) for k in ('common_config_sha256','common_prompt_sha256','implementation_sha256')}
        lines.append(f'各条件最近一次实际进入任务的对照组：{list(primary)}；共同身份种类数：{groups}。'
            '完整重试仍在上表，不择优。共享case/seed不保证初始RGB逐位相同，初始传感器哈希在attempts.json中保留。')
        sensor_kinds={key:len({r['initial_sensor_hashes'].get(key) for r in batch})
            for key in ('cam_head_depth','cam_head_intrinsic_matrix','cam_head_extrinsic_matrix','rgb')}
        lines.append(f'该批初始头部深度/标定/RGB的哈希种类数：{sensor_kinds}。')
        differences=[v['mean_absolute_channel_difference_0_255'] for r in batch for v in r['public_vs_teacher_rgb']]
        if differences:
            lines.append(f'感知RGB与同step的原Astra头部RGB来自相邻两次公开采集，期间未执行动作，'
                f'但渲染不逐位一致；各帧平均通道差范围{min(differences):.4f}–{max(differences):.4f}（0–255量程）。'
                '帧版本一致不代表图片逐位相同，完整差异审计保留。')
    lines += ['', '## LingBot-Depth的真实离线接入', '']
    probe=ROOT/'results/hybrid-lingbot-recorded-20261013-v2'
    if (probe/'frame/evidence.json').exists():
        evidence=read(probe/'frame/evidence.json');compare=read(probe/'comparison_to_clean_rendered_depth.json')
        difference=compare['regions']['target_mask']
        lines += [f'同一公开录制帧，官方v0.5权重实际前向{evidence["depth_refinement"]["inference_s"]:.3f}秒；'
            f'SAM文本分割目标数{len(evidence["objects"])}。resolution_level=0，不是默认9档速度。',
            f'原生输入深度完全有效；预测与原生深度在目标mask内RMSE={difference["rmse_m"]*100:.2f}cm，'
            f'MAE={difference["mae_m"]*100:.2f}cm，p95绝对差={difference["p95_abs_difference_m"]*100:.2f}cm。'
            '这是与干净渲染深度的比较，没有证明对真实传感器更差或更好。',
            '第一次推理因缺少xFormers嵌套张量依赖失败，保留日志；隔离安装匹配原torch2.7的'
            'xformers0.0.30后真实推理通过。源码与1.28GB权重有固定来源与哈希，没有替换模型。',
            f'[几何差异]({probe}/comparison_to_clean_rendered_depth.json)；[模型来源/运行身份]({probe}/model_identity.json)。']
        if (probe/'depth-comparison.png').exists():
            lines += ['',f'![同一铲子裁剪：RGB、原深度、LingBot精修及深度差]({probe}/depth-comparison.png)',
                '两幅深度图共用色标；差值图以厘米表示，显示范围截断到±5cm。']
    audit=ROOT/'results/lingbot-depth-audit-20261013/results.json'
    if audit.exists():
        lines += ['', '## 同一公开帧的深度质量/缺失消融', '',
            '干净渲染深度仅用于评测参考，退化推理只输入退化深度。固定随机seed=41；'
            '同一SAM mask、同一RGB。误差均对干净渲染深度计算，不是真实传感器精度或Astra任务成功率。', '',
            '| 输入条件 | 档位 | 前向(s) | 目标输入覆盖 | 目标输出覆盖 | 目标输入RMSE(cm) | 目标输出RMSE(cm) | 目标缺失区输出RMSE(cm) | 目标原有效区输出RMSE(cm) |',
            '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
        def cm(value):return '—' if value is None else f'{100*value:.2f}'
        for row in read(audit)['rows']:
            m=row['metrics'];target=m['target_mask']
            lines.append(f'| {row["corruption"]} | {row["resolution_level"]} | {row["inference"]["inference_s"]:.3f} | '
                f'{target["input"]["coverage"]:.1%} | {target["refined"]["coverage"]:.1%} | '
                f'{cm(target["input"]["rmse_m"])} | {cm(target["refined"]["rmse_m"])} | '
                f'{cm(m["target_missing"]["refined"]["rmse_m"])} | {cm(m["target_retained"]["refined"]["rmse_m"])} |')
        lines.append(f'[全部区域指标与模型身份]({audit})。冷/热前向顺序不同，单次耗时不构成稳定吞吐基准。')
        chart=audit.parent/'target-depth-audit.png'
        if chart.exists():
            lines += ['',f'![目标深度覆盖与误差]({chart})',
                '输入误差仅统计原有效像素；空洞不是零误差。输出误差包含补全后的像素，'
                '区域不同，须结合覆盖率及缺失/原有效区分项解读。']
    lines += ['', '## 当前结论与下一步', '',
        '本轮为小规模真实Astra任务开发对照。只按实际完成/预算中断报告，不从少量尝试估计架构成功率。'
        '也不拿旧本地自主抓取88秒与新Astra hybrid直接比较来宣称感知改善。',
        'SAM+LingBot组只在首段引用感知确认目标侧，后续公开理由明确说表面估计未改变决策；'
        '遮挡时SAM还会返回无目标。单次终止成功不能归因于LingBot，也没有证明泛化或420秒多次抓放。'
        '该组Astra累计等待340.58秒，LingBot热前向约0.08秒；当前速度瓶颈仍是Astra调用，'
        '仅加快感知无法解决，应继续测低层动作分块执行与事件触发Astra复核。',
        '无上游失败响应的SAM+原始深度补跑也在57步成功，历史时间上界395.43秒；'
        '因此现有结果没有显示LingBot优于原始深度。H0/H1分别54/47步预算内未完成，'
        '这些单次差异仍混有模型响应时间、决策分块及轨迹波动，不能估计加SAM的净收益。',
        '本轮感知进程常驻，但只在Astra获取新观测时推理，更新间隔仍跟随原工具循环；'
        '尚未测试后台持续感知和异步执行。0.08秒是前向耗时，不是当前端到端更新频率。',
        '先核对动作确实使用感知，再对冻结的未见布局重复。优先检验理想深度/空洞/噪声分层，'
        '表示消融（叠图/结构化几何）和更新机制；随后接入单目米制模型与检测/跟踪备选，'
        '最后扩至放置、420秒多轮与实机。',
        f'[已有方法调查]({ROOT}/experiments/perception-manipulation/perception-survey.zh-CN.md)；'
        f'[主对照计划与命令]({ROOT}/experiments/perception-manipulation/astra-hybrid-plan.zh-CN.md)。', '']
    (out/'report.zh-CN.md').write_text('\n'.join(lines))
    print(out/'report.zh-CN.md')


if __name__=='__main__':main()
