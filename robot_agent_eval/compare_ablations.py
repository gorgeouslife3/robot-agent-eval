"""Report every development attempt without mixing replay and live model runs."""
from pathlib import Path
import json
from .common import ROOT,read,write


def main():
    out=ROOT/'results/perception-manipulation-ablation';out.mkdir(parents=True,exist_ok=True)
    runs=[]
    for p in sorted((ROOT/'runs').glob('20261013-*/result.json')):
        result=read(p)
        if result['method'] not in ('modular_pickup','modular_calibration','public_calibration','graspnet_calibration'):continue
        d=p.parent;failure=read(d/'controller/failure.json') if (d/'controller/failure.json').exists() else {}
        errors=[]
        if (d/'model_requests.jsonl').exists():
            errors=[r for r in map(json.loads,(d/'model_requests.jsonl').read_text().splitlines()) if r.get('error_type')]
        trace=[]
        if (d/'controller/framework_trace.jsonl').exists():
            trace=list(map(json.loads,(d/'controller/framework_trace.jsonl').read_text().splitlines()))
        runs.append(dict(run=str(d),result=result,experimental_scope='development on previously used shovel layout1',
            primary_generalization_comparison_eligible=False,controller_error=failure,model_errors=errors,
            stages=[r for r in trace if r.get('event') in ('local_move_end','grasp_verification','recorded_semantic_seed','local_height_evidence')]))
    write(out/'attempts.json',runs)
    lines=['# 感知与操作替换：首批开发试验', '',
        '日期：2026-10-13。所有原生运行均为 RoboDojo 仿真；尚未进行实机或多轮放置。',
        '本轮使用已参与 skill 开发的铲子 layout1，不能估计泛化成功率。', '',
        '## 实际完成的工作', '',
        '- 统一 RGB-D 几何与操作接口，接入三种感知条件：Astra RGB 位置估计、Astra 像素+深度、初始 Astra 选目标后 SAM+深度。',
        '- 感知对照共享几何抓取、原版有步幅限制的机器人 DLS 执行器；真实定位坐标进入预抓取、下降和抬升目标。另有真实Contact-GraspNet候选执行条件，共享DLS。',
        '- 共享本地试抬判定，并设置恢复开关。几何执行不标记为 GraspNet/VLA。',
        '- 保存模型请求、传感器、代码/配置身份、目标与实测 TCP、全部失败；429 不记为机械抓取失败。', '',
        '## E0：接口检查', '',
        '首个原生校验重置超时（无控制步），已保留。重跑 public_calibration 完成两次保持动作、完整姿态与位置 IK；'
        'modular_calibration 完成一次 DLS 保持动作，实测位置/角度变化为零。',
        '实际深度309点的反投影/投影代数往返误差约3.33e-7像素、2.56e-9米；这不证明实机外参精度。', '',
        '## E1 / E2 / E4：录制帧试验', '',
        '首个录制批次遇到缺标定的旧RGB-only输入而停止；v2完成3次Astra请求后在SAM导入处停止；'
        '修正后v3复用传感器校验匹配的原始选择并完成本地分割/几何。失败没有覆盖或重算成成功。',
        f'[首批失败]({ROOT}/results/perception-ablation-pilot-20261013/failure.json)；'
        f'[v2失败]({ROOT}/results/perception-ablation-pilot-20261013-v2/failure.json)。', '']
    recorded=ROOT/'results/perception-ablation-pilot-20261013-v3'
    if (recorded/'summary.json').exists():
        summary=read(recorded/'summary.json');rows=read(recorded/'results.json')
        lines += [f'3张匹配的初始帧：真实 Astra 请求原始总等待 {summary["astra_wait_s"]:.2f} 秒；'
                  f'SAM 点提示分割累计 {summary["sam_current_seed_s"]:.3f} 秒。',
            '后续复用了原始已付出的目标选择，未再次发送模型请求；模型成本仍归原始运行。', '',
            '| 帧 | Astra等待(s) | SAM点提示(s) | 深度几何(s) | RGB估计与单点深度位置差(m) |',
            '|---|---:|---:|---:|---:|']
        for r in rows:
            lines.append(f'| {r["index"]} | {r["astra_elapsed_s"]:.2f} | {r["sam_point"]["elapsed_s"]:.3f} | '
                         f'{r["depth_geometry_elapsed_s"]:.4f} | {r["rgb_vs_depth_agreement_m"]:.4f} |')
        lines += ['', '三帧的 SAM、局部主轴和单初始语义种子定位均完成。它们来自同一布局重置，前两帧深度校验值相同；'
                  '不是独立布局，也不是动态跟踪成功率。RGB与深度差只表示一致性，无物体真值时不能称定位误差。',
            f'[逐帧数据]({recorded}/results.json)；[真实请求与原始目标选择]({ROOT}/results/perception-ablation-pilot-20261013-v2/manifest.json)。', '']
    lines += ['## E6：Contact-GraspNet真实推理', '']
    grasp=ROOT/'results/contact-graspnet-probe-20261013'
    if (grasp/'result.json').exists():
        g=read(grasp/'result.json')
        lines += [f'真实 RGB-D + SAM mask，一次 Contact-GraspNet 前向：{g["full_points"]:,}个场景点、'
            f'{g["segment_points"]:,}个目标点，返回{g["candidates"]}个候选，推理{g["inference_s"]:.3f}秒，'
            f'模型构建/权重加载{g["load_s"]:.3f}秒（进程启动另计），最高分{g["max_score"]:.3f}。',
            '来源为 elchun 的第三方 PyTorch 实现（非官方 TensorFlow 实现），固定提交2d71da4e；'
            '已用Git树校验源文件和权重，应用ASPIRE已有的3文件兼容补丁。完整源码压缩包下载超时，'
            '未取得的尾部示例文件不用于推理，记录不宣称压缩包完整。',
            '候选原点是Panda抓手基座，使用原库平面指垫中心Z=0.1034m转换到接触中心，再转换到ARX link6。'
            '下方单列原生静态IK和实际执行尝试。候选得分不是成功概率。机器人执行仍用共享DLS，'
            '先按语义抓取点距离≤4cm、近顶部接近、预测开口≤6.5cm过滤，再按分数选择；这不是纯分数抓整物体对照。',
            f'[推理记录]({grasp}/result.json)；[候选数组]({grasp}/candidates.npz)；[来源身份]({grasp}/identity.json)。', '']
    elif (grasp/'failure.json').exists():
        lines += [str(read(grasp/'failure.json')), '']
    lines += ['## 原生逐次尝试：不挑选成功、不隐藏重试', '',
        '| 尝试 | 条件 | 状态 | 任务时间(s) | 控制步 | 模型请求 | 原生成功 |',
        '|---|---|---|---:|---:|---:|---|']
    for row in runs:
        r=row['result'];a=r.get('ablation') or {};d=Path(row['run'])
        condition=r['method'] if r['calibration'] else a['perception']+(' / GraspNet' if a.get('action_backend')=='contact_graspnet_dls' else ' / geometry')+(' / shallow-fault' if a.get('controlled_fault') else '')+(' / recovery' if a.get('recovery') else '')+(' / recorded-seed' if a.get('recorded_seed_controller') else '')+(' / anchor-verifier' if a.get('verifier') else ' / text-verifier')
        duration=r['timing'].get('episode_active_wall_s');seconds=f'{duration:.2f}' if duration is not None else '—'
        lines.append(f'| [{d.name}]({d}/result.json) | {condition} | {r["status"]} | {seconds} | '
            f'{r["native_steps"]} | {r["model_requests"]} | {r["native_success"]} |')
    lines += ['', '首个SAM深度动作试跑用1次Astra请求，推进84步：对齐、下降、闭合、3cm试抬。'
        '随后文本SAM目标分数0.113低于固定0.2阈值，验证终止；未产生独立原生成功判分。',
        '后续anchor-verifier条件作为新开发版本。实时配对组出现模型服务HTTP429，'
        '保留缺失用量为未知，不能将这些尝试用于感知/抓取成功率对比。',
        'recorded-seed条件明确复用早先Astra在公开RGB上的选择，要求初始深度/标定完全相同，'
        '用于检验动作/验证/恢复，不是独立从零Astra样本；不能忽略原始语义选择成本。', '',
        '## E10：可控空抓与本地恢复', '']
    for row in runs:
        r=row['result'];a=r.get('ablation') or {}
        if not a.get('controlled_fault'):continue
        verdicts=[s for s in row['stages'] if s.get('event')=='grasp_verification']
        lines.append(f'- 恢复={a["recovery"]}，首次闭合故意高于测得铲柄35mm：'
            f'{r["native_steps"]}步，活动时间{r["timing"].get("episode_active_wall_s",0):.2f}秒，'
            f'本地试抬判定{[v["verified"] for v in verdicts]}，原生成功={r["native_success"]}。'
            f'[记录]({row["run"]}/result.json)。')
    lines += ['', '关闭恢复的条件在未验证抓取时主动停止，原生分数未知，预算内完成为否；'
              '不把未知分数写成原生失败。普通无故障回放两次首次抓取均成功，不能用于证明恢复增益。',
        '验证器仍有待排查：恢复后第二次试抬的mask中位高度为0.884m，而同期实测TCP为0.810m；'
        '可能存在物体姿态变化或分割身份漂移，尚未区分。最终成功有独立原生判分支持，'
        '但不能由这一对故障试验宣称验证器可靠。后续需保存每次mask并检验错目标、空抓误判与滑落。', '',
        '## E6：原生可达性与候选执行', '']
    for row in runs:
        d=Path(row['run']);r=row['result']
        if (d/'controller/graspnet_reachability.json').exists():
            receipt=read(d/'controller/graspnet_reachability.json')
            lines.append(f'- 静态IK：{receipt["reachable_both_stages"]}/{len(receipt["candidates"])}个候选至少一臂在预抓取与抓取两阶段均可达；'
                f'{r["native_steps"]}控制步。[完整姿态/IK回执]({d}/controller/graspnet_reachability.json)。')
        if (r.get('ablation') or {}).get('action_backend')=='contact_graspnet_dls':
            lines.append(f'- 真实GraspNet候选+DLS执行：{r["status"]}，{r["native_steps"]}步，'
                f'活动时间{r["timing"].get("episode_active_wall_s",0):.2f}秒，原生成功={r["native_success"]}；'
                f'[记录]({d}/result.json)。')
            if (d/'controller/graspnet/result.json').exists():
                g=read(d/'controller/graspnet/result.json')
                lines.append(f'  同进程在线输入：{g["candidates"]}个候选，前向{g["inference_s"]:.3f}秒，'
                    f'构建/加载{g["load_s"]:.3f}秒；[数值精度设置]({d}/controller/graspnet/numeric_runtime.json)。')
    lines += ['', '前两次SAM/GraspNet同进程执行均在控制前发生CUDA邻域索引错误；关闭TF32仍失败。'
        '检查发现SAM3 tracking predictor构造时进入CUDA BF16 autocast且长期保留。'
        '第三次显式禁用GraspNet autocast并禁用TF32后，真实候选推理和机器人执行通过；'
        '日志记录继承的BF16状态。此前失败保留，属于部署兼容性故障，不并入机械抓取成功率。']
    lines += ['', '静态IK不能替代轨迹碰撞检查。预测Panda开口仅用于固定筛选，未证明其质量分数与ARX夹爪匹配；'
        '实际单场景执行结果不证明跨夹爪/跨物体泛化。', '',
        '## 时间与当前结论', '',
        '局部分割热推理约0.15秒、局部深度几何约0.007秒；真实Astra目标选择约50–83秒。'
        '这支持把重复感知交给本地模块，但推理倒数不是机器人闭环频率；'
        '当前仍按动作阶段更新，动态跟踪、移动目标和事件触发尚未验证。',
        '无故障SAM-depth几何回放两次原生成功：88.38/88.61秒；GraspNet候选回放一次原生成功：91.42秒；'
        '可控空抓恢复成功111.46秒。全部为单场景开发样本，不计算架构成功率或显著差异。',
        '上述活动时间含本轮本地加载/感知/动作/记录，但不含历史语义种子的82.71秒。'
        '例如将历史选择成本与88.38秒几何执行直接相加为171.09秒，仅是成本拆分估算，'
        '不是实测从零端到端成功时间；模拟器启动/重置另列在逐次result.json中。',
        '当前仅验证抓取与抬升。没有放置、多轮任务或实机数据，不能用420秒除以单次抬升时间来承诺抓放次数。', '',
        '## 工程验证', '',
        '38项现有与新增接口/几何测试通过，Python编译检查通过。'
        '另在主动启用BF16 autocast的调用上下文里再次运行真实GraspNet：8个候选、1.074秒前向，'
        '确认推理结束后还原TF32设置并保留调用方autocast状态；该项是兼容性回归，不计机器人抓取次数。',
        f'[测试日志]({ROOT}/results/perception-ablation-tests-final.log)；'
        f'[精度回归回执]({ROOT}/results/graspnet-precision-regression-20261013/context_regression.json)。', '',
        '## 后续验证', '',
        '在模型服务正常时重跑实时配对组，并对共享感知/执行器的几何与GraspNet条件做足重复。'
        '首先检查验证mask的物体身份与遮挡，再冻结接口并扩展未见布局；'
        '随后接入消费目标/ROI的VLA对照、放置与420秒连续循环。VLA本轮尚未接入。',
        f'[完整实验计划]({ROOT}/experiments/perception-manipulation/plan.zh-CN.md)；'
        f'[可重跑命令]({ROOT}/experiments/perception-manipulation/README.zh-CN.md)。', '']
    (out/'report.zh-CN.md').write_text('\n'.join(lines))
    print(out/'report.zh-CN.md')


if __name__=='__main__':main()
