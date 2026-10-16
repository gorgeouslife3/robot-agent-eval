> 本文保留原工作目录的历史说明。首次安装、协作与发布版复现步骤请从 [README.md](README.md) 开始。

# RoboDojo 本机具身 agent 评测

这是实际运行用的工作目录。原始 RoboDojo 位于 `/path/to/RoboDojo`；这里保存代码快照、冻结的布局清单、评测适配代码和每次尝试的完整记录。**已下载源码不等于已完成评测。**

当前用户指定：GPT-6 Astra、Responses 接口、先小规模验证。模型配置只引用本机密钥文件，报告不保存密钥。仿真与模型工具运行在不同进程中；模型请求经过仅绑定本机的计数代理，真正的密钥不交给控制 agent 的脚本。

## 已实现的入口

新增单场景初版：`astra_react_skill`。使用短观察循环与淡紫色塑料铲子任务skill，
独立于原版Direct；[设计和运行说明](harness/README.zh-CN.md)、
[任务skill](harness/skills/robodojo-shovel-pickup/SKILL.md)。
`python -m robot_agent_eval.compare_shovel`生成该场景的token、时间和逐段动作对照。
RPent、GaP 与 PhyAgentOS 已增加本机适配与逐次记录，
[框架比较报告](results/shovel-framework-comparison/report.zh-CN.md)保留全部尝试，
包括接口故障、生成代码失败及原生结果；[运行说明](FRAMEWORK-PILOT.md)列出各条件命令。
使用 `.venvs/frameworks/bin/python -m robot_agent_eval.compare_frameworks` 刷新报告。

```bash
cd /path/to/robot-agent-eval

# 查看方法登记表；它不是一组已经实现的控制器。
python -m robot_agent_eval.cli methods

# 冻结任务、布局及原生代码身份，不启动 GPU。
python -m robot_agent_eval.cli inventory

# 一次真实模型请求，仅验证接入，不算机器人试验。
python -m robot_agent_eval.api_probe

# 原版 Codex 工具接口启动检查，不发送模型请求。
/path/to/robodojo-env/bin/python -m robot_agent_eval.controller_preflight

# 保持初始关节位置至原生终止：仅检查评测链路。
python -m robot_agent_eval.runner --method hold_calibration

# 原版 Astra Direct 工具循环，指定已冻结的任务和布局。
python -m robot_agent_eval.runner --method astra_direct \
  --manifest manifests/pilot.json --task general_pickup --layout 1 \
  --config configs/model.pilot.json

# 重新汇总所有尝试；不同预算不合并，重试不挑最好的一次。
python -m robot_agent_eval.aggregate

python -m unittest discover -s tests -v
```

π₀.₅-only 与 Hybrid 的入口分别使用 `--method pi05_only` 和 `--method astra_hybrid`；同一 `general_pickup --layout 1` 可作首项配对检查。策略默认使用 `.venvs/openpi-existing/bin/python`，继承本机已有 OpenPI 库，并优先加载 `runtime-sources/openpi` 中锁定的源码。实际版本/差异见 `openpi-runtime-preflight.json` 和每次运行中的 `policy_runtime.json`。入口实现并不代表实际推理已验证，以运行结果为准。

## 看什么文件

- `report.zh-CN.md`：方法差异、统一评测约定、当前适配情况。
- `results/attempts.json`、`results/summary.json`：实测逐次结果和汇总。
- `results/paired-primary.json`：Direct、Hybrid、π₀.₅-only 都测过的共同案例；不把任务覆盖不同的样本直接排名。
- `results/shovel-framework-comparison/`：框架详细对照、skill 来源、每轮原始文字审计，以及规划/图像/验证的分项用量。
- `runs/<试验名>/result.json`：这一次的原生结果、预算状态、时间与模型用量。
- `runs/<试验名>/sim/sensors.mp4`：实际执行的三视角视频；播放速度是仿真时间，不能拿视频长度当现实耗时。
- `runs/<试验名>/controller/history.json`：模型公开给出的动作理由、目标和执行回执。
- `runs/<试验名>/controller/edit_NNN.json`：目标与关节转换的诊断，能检查“说要到那里”和“机械臂实际到了哪里”的差距。
- `runs/<试验名>/observed_tracking.json`：把模型要求的手部姿态与执行后的实测姿态对照；它不测量物体定位或夹持接触。
- `runs/<试验名>/model_requests.jsonl`：真实模型请求计数、等待时间、服务返回的 token 用量。
- `runs/<试验名>/model_request_starts.jsonl`：新版本在请求发起时记录，避免预算停止导致未返回请求消失；首批旧记录可能没有此文件，完整性见结果中的 `model_usage_complete`。
- `runs/<试验名>/sim/initial_observation_fingerprint.json`：实际初始化后的图像、机械臂状态校验值。
- `source-lock.json`：各仓库版本、下载状态；来源网页或缺少控制器也明确标记。
- `manifests/`：2100 个原生测试布局、579 个额外开发布局、21 个接口试验布局。

## 结果含义

成功由 RoboDojo 原生判定条件决定。模型说“完成”、机械臂确实动了、进程退出码是 0，都不能替代原生成功。模型预算耗尽时，`native_success` 和 `native_score` 保持未知；`success_within_budget=false` 表示在给定资源内没有完成任务。原生无效布局、模型服务中断和部署/传输异常另列，不伪装成抓取失败。生成的程序读错接口字段属于方法执行失败，仍不编造尚未发生的原生终止分数。

`model.local.json` 是较小的接入预算；`model.pilot.json` 是第二轮预算校准：最多 60 次真实模型请求、60 次控制决策、累计 200 万 token、控制进程 1200 秒。累计 token 包括缓存输入，**不等于货币费用**。token 限制在一次响应后检查，最后一次请求可能使累计量略超上限；代理对请求次数则在发送前限制。费用价格尚未提供，金额保持未知。

这是能力与资源的试验，不是保证成功的运行脚本。每次启动生成新目录，失败不会被覆盖。代理、控制器和仿真只清理本次拥有的进程。为了阻止模型通过文件读取测试布局、隐藏场景状态或密钥，评测 wrapper 加了显式文件权限限制。原版提示词与完整工具循环保留；部署差异见报告。

诊断入口 `--method pi05_discard_first` 丢弃一次初始策略提议，不做任何物理动作，然后从同一观测重新推理。它用于研究重新采样的影响，结果单列，不并入原版 π₀.₅-only。首轮同一铲子场景中 Direct、Hybrid 成功，π₀.₅-only 和该诊断条件失败；另有 Direct 排列方块预算内未完成。这些小样本只说明链路能运行，不构成全量成功率排名。
