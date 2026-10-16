# 同一铲子场景：Astra、RPent、GaP、PhyAgentOS 实测

冻结案例 `general_pickup:seed0:layout1`；任务为“把淡紫色塑料铲子抬高 10 cm”。所有语言、图像分析与验证请求统一为 gpt-6-astra / xhigh；控制模型为同一 RoboDojo π0.5 权重。200 个原生控制步、每秒 25 步，不允许重置重试。

**这是接口开发中的单场景试跑。** 该布局参与了自定义 skill 开发；历史对照与新框架的输入、动作粒度及预算配置不同，不能据此得出泛化成功率或公平的架构排名。下面保留初始化、图生成、连接故障和所有重试。

SAM3 官方权重已下载、校验并用于真实分割：[下载身份记录](../sam3-download.json)。GaP 的 Grounding DINO 也已实跑：[下载身份记录](../grounding-dino-download.json)。接口与记账的 27 项检查通过：[检查记录](../framework-validation.json)。

## 当前结果速览

各条件按时间列出最近一次已结束尝试，便于阅读；完整重试记录紧随其后，未筛选最好结果，以下不是成功率。GaP 复用图的生成成本另见后文。

| 条件 | 最近尝试的结果 | 任务时间(s) | 步 | 请求 | 输入token | 缓存输入 | 输出token |
|---|---|---:|---:|---:|---:|---:|---:|
| [Astra Direct](../../runs/20261008-170459-975772-astra_direct-general_pickup-l1/result.json) | 成功 | 775.84 | 71 | 25 | 2,082,807 | 1,972,224 | 7,131 |
| [Astra Hybrid](../../runs/20261008-180207-968322-astra_hybrid-general_pickup-l1/result.json) | 成功 | 424.22 | 58 | 16 | 1,068,087 | 983,808 | 5,035 |
| [π0.5-only](../../runs/20261008-175803-426113-pi05_only-general_pickup-l1/result.json) | 失败 | 79.13 | 200 | 0 | 0 | 0 | 0 |
| [ReAct + 铲子 skill](../../runs/20261011-175055-152063-astra_react_skill-general_pickup-l1/result.json) | 成功 | 552.45 | 130 | 26 | 89,887 | 0 | 12,437 |
| [RPent](../../runs/20261011-212848-178623-rpent_astra-general_pickup-l1/result.json) | 失败 | 232.72 | 200 | 4 | 18,340 | 0 | 265 |
| [GaP（本轮复用图）](../../runs/20261011-221044-073562-gap_astra-general_pickup-l1/result.json) | 执行程序出错（原生分数未知） | 45.37 | 0 | 2 | 9,746 | 3,968 | 126 |
| [PhyAgentOS 官方 skill](../../runs/20261011-221746-476840-phyagentos_official_astra-general_pickup-l1/result.json) | 失败 | 865.36 | 200 | 56 | 1,326,413 | 222,080 | 12,451 |
| [PhyAgentOS 定制 skill](../../runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/result.json) | 预算内未完成（原生分数未知） | 1175.03 | 58 | 52 | 747,531 | 191,616 | 23,502 |

## 全部尝试

| 方法 / 每次尝试 | 原生结果 | 状态 | 任务时间(s) | 控制步 | 请求 | 输入token | 缓存输入 | 输出token |
|---|---|---|---:|---:|---:|---:|---:|---:|
| [20261008-170305-174993-astra_direct-general_pickup-l1](../../runs/20261008-170305-174993-astra_direct-general_pickup-l1/result.json) | 未完成/未知 | controller_error | — | 0 | 0 | 0 | 0 | 0 |
| [20261008-170459-975772-astra_direct-general_pickup-l1](../../runs/20261008-170459-975772-astra_direct-general_pickup-l1/result.json) | 成功 | native_completed | 775.84 | 71 | 25 | 2,082,807 | 1,972,224 | 7,131 |
| [20261008-175803-426113-pi05_only-general_pickup-l1](../../runs/20261008-175803-426113-pi05_only-general_pickup-l1/result.json) | 失败 | native_completed | 79.13 | 200 | 0 | 0 | 0 | 0 |
| [20261008-180207-968322-astra_hybrid-general_pickup-l1](../../runs/20261008-180207-968322-astra_hybrid-general_pickup-l1/result.json) | 成功 | native_completed | 424.22 | 58 | 16 | 1,068,087 | 983,808 | 5,035 |
| [20261011-175055-152063-astra_react_skill-general_pickup-l1](../../runs/20261011-175055-152063-astra_react_skill-general_pickup-l1/result.json) | 成功 | native_completed | 552.45 | 130 | 26 | 89,887 | 0 | 12,437 |
| [20261011-204241-426801-rpent_astra-general_pickup-l1](../../runs/20261011-204241-426801-rpent_astra-general_pickup-l1/result.json) | 未完成/未知 | adapter_init_error | — | 0 | 0 | 0 | 0 | 0 |
| [20261011-204604-277539-gap_astra-general_pickup-l1](../../runs/20261011-204604-277539-gap_astra-general_pickup-l1/result.json) | 未完成/未知 | controller_error | — | 0 | 16 | 169,748 | 21,504 | 10,269 |
| [20261011-204734-813398-rpent_astra-general_pickup-l1](../../runs/20261011-204734-813398-rpent_astra-general_pickup-l1/result.json) | 未完成/未知 | infrastructure_error | — | 0 | 0 | 0 | 0 | 0 |
| [20261011-210259-128093-phyagentos_custom_astra-general_pickup-l1](../../runs/20261011-210259-128093-phyagentos_custom_astra-general_pickup-l1/result.json) | 未完成/未知 | native_transport_error | — | 5 | 20 | 180,683 | 12,800 | 8,489 |
| [20261011-212157-619323-rpent_astra-general_pickup-l1](../../runs/20261011-212157-619323-rpent_astra-general_pickup-l1/result.json) | 成功 | native_completed | 171.99 | 157 | 4 | 16,151 | 0 | 286 |
| [20261011-212848-178623-rpent_astra-general_pickup-l1](../../runs/20261011-212848-178623-rpent_astra-general_pickup-l1/result.json) | 失败 | native_completed | 232.72 | 200 | 4 | 18,340 | 0 | 265 |
| [20261011-213452-358159-gap_astra-general_pickup-l1](../../runs/20261011-213452-358159-gap_astra-general_pickup-l1/result.json) | 未完成/未知 | controller_error | 77.58 | 0 | 6 | 94,766 | 0 | 1,651 |
| [20261011-213947-111735-gap_astra-general_pickup-l1](../../runs/20261011-213947-111735-gap_astra-general_pickup-l1/result.json) | 未完成/未知 | native_transport_error | — | 0 | 18 | 222,851 | 15,104 | 9,563 |
| [20261011-215326-741991-gap_astra-general_pickup-l1](../../runs/20261011-215326-741991-gap_astra-general_pickup-l1/result.json) | 未完成/未知 | native_transport_error | — | 0 | 17 | 203,193 | 40,576 | 12,880 |
| [20261011-220521-421225-gap_astra-general_pickup-l1](../../runs/20261011-220521-421225-gap_astra-general_pickup-l1/result.json) | 未完成/未知 | native_transport_error | 3.54 | 0 | 0 | 0 | 0 | 0 |
| [20261011-221044-073562-gap_astra-general_pickup-l1](../../runs/20261011-221044-073562-gap_astra-general_pickup-l1/result.json) | 未完成/未知 | controller_error | 45.37 | 0 | 2 | 9,746 | 3,968 | 126 |
| [20261011-221746-476840-phyagentos_official_astra-general_pickup-l1](../../runs/20261011-221746-476840-phyagentos_official_astra-general_pickup-l1/result.json) | 失败 | native_completed | 865.36 | 200 | 56 | 1,326,413 | 222,080 | 12,451 |
| [20261011-223519-789805-phyagentos_custom_astra-general_pickup-l1](../../runs/20261011-223519-789805-phyagentos_custom_astra-general_pickup-l1/result.json) | 未完成/未知 | adapter_contract_error | 56.76 | 0 | 7 | 34,202 | 5,888 | 520 |
| [20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1](../../runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/result.json) | 未完成/未知 | wall_budget | 1175.03 | 58 | 52 | 747,531 | 191,616 | 23,502 |

任务时间从重置完成到原生结束或停止，包含模型、控制和记录；启动、重置、退出另计。缓存已经包含在输入里，不能再相加。输出包含服务报告的推理用量。所有请求都计入，包括图编译、看图、验证、报错前调用和收尾；价格未提供，不推算费用。连接断掉且没有原生结束记录时，分数保留未知；从 RPC 日志恢复的控制步只是已记录下限。

## 实际输入了什么，skill 来自哪里

| 条件 | 文本与图片输入 | skill / 记忆来源 |
|---|---|---|
| Astra Direct | 原库控制说明、任务文字、机器人姿态、三相机 RGB、持续 Codex 工具记录；模型自己决定手部目标 | 原版提示词，没有注入我们的铲子 skill |
| Astra Hybrid | 与 Direct 同一类说明和观测，另有 π0.5 提出的关节动作及经机器人运动学计算的手部轨迹 | 原库监督提示词；没有未来物理仿真，也没有我们新增的铲子 skill |
| ReAct + skill | 简短控制说明、当前/上一幅图、测得手部姿态、剩余预算、上次动作回执、任务文字 | 我们的 robodojo-shovel-pickup；同时改变了上下文组织，不能把全部收益归因于 skill |
| RPent | 原库 RoboDojo SYSTEM/USER，先读 view_env_state 得到真实任务文字；SAM3 分割、深度定位、运动/VLA 工具的结果进入后续对话 | 原库工具、提示词和 MemoryManager；未注入我们的 skill。官方 HF 记忆库未发布 RoboDojo 条目，本轮没有场景记忆可读 |
| GaP | 任务文字 + 本机机器人接口说明（双臂、抓取中心、预算），原库协调/子图/检查提示词，以及所选原 skill 文档和规范脚本 | 原 gap_skills；没有我们的铲子 skill。具体所选 skill 看各次 workflow 与下方记录 |
| PhyAgentOS 官方 | 任务文字、冻结批次参数、gpt6_pi05 接口说明，原 AgentLoop 上下文、激活后的文档、工具状态；image 工具另向同一 Astra 发图片并返回描述 | 官方 registry 的 robodojo 0.2.1。文档主要教如何跑批次、监督 π0.5 和处理回执，并非铲子抓取教程 |
| PhyAgentOS 定制 | 原 AgentLoop + 当前任务 + 定制文档 + Forge 工具/任务记录；图片经原 image 工具分析 | phyagentos-shovel-pickup，改编自我们旧 skill，按其任务绑定、动作回执、证据与复核机制重写；不是官方 skill |

[官方 RPent 记忆库检查](../rpent-memory-audit.json)；[PhyAgentOS 官方资源身份](../phyagentos-robodojo-registry.json)；[定制文档](../../harness/skills/phyagentos-shovel-pickup/SKILL.md)。

Phy 两组还实际激活了仓库自带的 supporting [image skill](../../source-snapshots/phyagentos/PhyAgentOS/skills/image/SKILL.md)。下面逐次列出 activate_skill 成功回执里的名称、来源与内容校验值；primary 任务 skill 与 supporting 图像说明分开追踪。

每次试验的 USER.md / SYSTEM.md、完整 model_input 和 text_provenance 是实际输入证据。下方的“文本审计”把每轮文本原样抽出、去重保存，并标记图片与工具说明所在位置；不凭配置宣称“模型读过了全部 skill”。历史 Direct/Hybrid 使用原 Codex 宿主，审计抽取其公开会话记录，并保留原 PROMPT.md / SKILL.md / 控制契约；这能核对会话文本，但不是每次重复 API 请求的完整抓包。

## 保留了什么，接入改了什么

- RPent 保留 RoboDojoToolkit、PromptBundle、MemoryManager、SAM3Client 和原动作工具；新增 Responses planner 接入同一工具循环，并把 public RoboDojo API 与真实 π0.5 接上。不是官方 CodexPlanner 全套宿主重现，也不是 Flash 无模型回放。
- GaP 保留原图生成、规范脚本、图执行器和 gap_skills。新增双 ARX X5 连接器，转换抓取中心与 link6 姿态；原 VLM、SAM3、Grounding DINO 工具逻辑保留，工具进程改为本机进程内调用。最新条件给原动作 skill 的生成工具目录补上本机 IK/姿态构造接口，文档与规范脚本不改；工具分发目标参数改为只能按位置传递，避免与工具自己的 name 字段冲突。当前缺少原 world_snapshot，语义 checkpoint 执行关闭；原生任务判分仍独立保存。这是移植条件，不是完整官方复现。
- PhyAgentOS 保留 AgentLoop、skill 激活与绑定、AgentTaskCoordinator、动作生命周期、证据记录和原验证规则；官方条件还保留 BridgeState。把 Dora 部署换为本机 HTTP Gateway，验证的子进程传输换为进程内运行。定制条件新增相对手部动作工具；它与官方 joint edit 不是相同控制能力。
- 框架只收到相机 RGB/深度/标定与机器人状态，没有物体真值、布局文件或奖励检查工具。RPent/GaP 需要原生 IK，Direct/ReAct/Phy 定制沿用有步幅限制的机器人运动学求解；两种执行器的能力差异应单独验证。
- 最新适配开启真实原生深度采集与相机标定；旧 RPent 尝试漏传深度，会明确列为接口开发条件。比较感知效果时，应把 RGB-only 与 RGB-D 条件分开。

原版 π0.5-only 每次只执行预测的前 15 步后重新看图；RPent 的 pi0_pick 按原工具执行最多 50 步，再生成下一段，且在手部抬升/夹爪启发式满足时提前停止。这会改变实际策略，即便权重、任务文字和模型随机种子相同，也不能把结果差异都归于 Astra。框架适配还逐步保存 RGB-D 文件，历史 Direct 每段记录；这部分额外记录成本计入墙钟，也影响速度对比。

本机 Phy 官方桥每个受监督段最多 10 步；定制手部动作每次最多 5 步。官方也可选择透传模式，让 π0.5 连续执行。RPent 一次 pi0_pick 则可连续做多段预测直到工具停止，不必每 10 步再请 Astra 判断。因此“模型请求少、任务更快”可能来自一次工具调用做得更多，并不自动说明规划更好。调用次数与原生控制步数需要同时看。

## 如何理解好坏与适用场景

Direct 的好处是新任务无需预先编动作图，模型可以直接看图调整；代价是反复看图、长上下文、工具调用很慢，精确位置和接触要靠执行反馈纠正。ReAct skill 能把已知场景的检查顺序写清楚，减少绕路与说明负担；它更依赖任务经验，换场景可能失效。

Hybrid 和 RPent 都可以把熟悉的运动交给 π0.5。区别在于 Hybrid 逐段接受/接管提议，RPent 把“分割、三维定位、移动、π0.5抓取”暴露为不同工具供模型选择。RPent 更容易记录是哪一步感知或动作失败，但更依赖传感器和工具接口；不能把工具自己的抓取启发式当作环境成功。

GaP 的重点是先把做法写成能执行的图，再按节点运行。重复任务可以复用图，减少在线规划；代价是第一次生成要付出成本，规范脚本和机器人接口必须匹配，生成代码出错时机械臂甚至还没动。本轮必须同时报告首次生成时间和执行时间，不能只展示执行速度。

本轮 GaP 通过校验的图来自 [215326 尝试](../../runs/20261011-215326-741991-gap_astra-general_pickup-l1/controller/generated_graph/task_00)，生成花费 471.48 秒、17 次请求、203,193 输入 token（含 40,576 缓存）、12,880 输出 token。后续 220521 与 221044 是明确标注的复用图条件，未重新生成，不能当作独立从零成功率样本。最新执行已完成 Grounding DINO、VLM、SAM3 与深度点云感知，拟合细柄并构造抓取姿态；随后生成的 select_reachable_arm.py 读取 result["joints"]，而原库与本机 IK 接口均返回 joint_config/positions。第一次不可达返回 success=false，脚本没有处理就触发 KeyError，尚未移动机械臂。图未人工改写来制造成功；这是生成脚本失败，原生完成与分数保留未知，预算内完成记失败。

PhyAgentOS 的重点是管理 skill、任务、动作回执与完成证据。它适合需要追踪任务、接口和恢复状态的系统，但本身不是一个更强的抓取模型；效果由所加载 skill 与底层控制工具决定。image 先返回文字描述、planner 再决策的路径带来额外调用与信息压缩，任务/回执/验证也有开销。定制 skill 的表现不能直接当作官方 skill 的表现。

资源预算也会直接影响这个比较：在 ReAct 中，一次带图决策就能产生动作；Phy 定制条件还要由 planner 调用 image、读取分析、启动动作并读取回执，经常需要几次模型请求才产生一段控制。同样的 60 次 API 上限，能支持的动作段数量因此不同。这是真实的执行开销，但要单独判断 skill 或规划能力，应另做相同动作工具、相同图像输入与相同控制反馈次数的对照，并保留不同总资源预算下的曲线。

Phy 官方本轮原生失败：200 步、865.36 秒、56 次请求。先做 5 段各 10 步，第 30 步后保持左夹爪打开以避免抓错刷子；第 50 步改用 student 连续模式，直到 200 步结束。终止后，AgentTask 的 finalize 还暴露本机 Gateway 回执不匹配：原状态端点应给 phase，结果端点应给 status=available/result，旧适配只给 status=succeeded，动作记录因此停在 accepted，语义验证没有启动。这是另一个收尾接线问题，不是此次原生失败的原因证明。官方记录保留原样；223519 定制启动在 0 控制步时被主动停止并单列 adapter_contract_error，修正回执且完成真实客户端契约测试后才重新运行定制条件。

修正回执后的 [Phy 定制组](../../runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/result.json)在 1200 秒控制进程预算内未完成，重置后任务活动时间 1175.03 秒，12 段动作共 58 步。全部保持右夹爪打开，主要做接近、旋转和水平对齐，尚未尝试闭合或抬升。模型等待已记录 1103.87 秒；52 次提交中有 51 次结束记录、50 次返回用量，747,531 输入（含 191,616 缓存）、23,502 输出 token 是记录下限。第 42 次请求等待 51.39 秒后收到 HTTP 502；image 工具把错误交给 planner，后者继续请求，最后第 52 次又因总时间停止而未返回。这两次用量未知，不能把模型/服务波动全部归因于架构。它仍在用腕部图像做移动试探，例如 -20mm 世界 x 位移后，模型观察到目标向图像右侧移动，再反向修正。记录支持“本轮感知确认和对齐耗时，未到抓取阶段”，不支持“底层抓取一定不行”。任务尚未 finalize，语义验证也没有启动，不能据此评价 verifier 是否有效。

![Phy 官方与定制组的起始和最终头部图像](phy-final-frames.png)

拼图只使用两组已记录的公开相机图像：[原始图片路径](phy-final-frames.sources.json)。原生成败以独立判分记录为准，图片不替代抬升高度测量。

RPent 两次已结束的尝试都调用 view_env_state → segment → back_project → pi0_pick，实际没有选择 scripted move_to。第一次深度接口缺失后仍原生成功，第二次定位正常却原生失败；不能据此说“深度让它变差”。两次初始机器人状态相同，但 RGB 像素非逐位相同，第一段预测已有小差异，后续状态差异扩大；这只是差异证据，不能单独证明失败原因。[比较记录](../rpent-repeat-observation-audit.json)。

还有一个关键的代码事实：这两次 pi0_pick 的参数分别为 right/max_chunks=10 与 right/max_chunks=5，没有传入刚算出的物体坐标。[原 pi0_pick](../../source-snapshots/rpent/robots/robodojo/tools.py:492)只把任务文字、RGB 和机器人状态交给 π0.5，内部不读 SAM3 分割点。其 arm 参数用于返回标签，抓取启发式实际检查双臂。因此本轮“先定位”并不意味着控制模型利用了定位结果，也不能说 RPent 的每种抓取都必须借助 SAM3。要检验定位是否改善抓取，需要单独评测真正消费三维位置的 move_to/抓取工具路径。

![两次 RPent 的初始与最终头部图像](../rpent-repeat-head-frames.png)

本轮不能据单次成败证明某种架构优越。下一轮应冻结适配器与 skill，用相同未见布局、相同预算重复运行；另外做 π0.5 的 15步/50步执行段消融、同一 ReAct 开关 skill、Phy 相同动作工具不同流程、GaP 首次生成与复用图两组。这样才能分辨提升来自模型、提示、控制粒度还是任务管理。

## 每次尝试的执行顺序与证据

### 20261008-170305-174993-astra_direct-general_pickup-l1

原生结果：未完成/未知；模型等待累计 0.00s；整次启动/执行/退出 16.51s。
模型提交请求 0 次，已结束记录 0 次；用量完整性：False。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261008-170305-174993-astra_direct-general_pickup-l1/index.json)；[控制目录](../../runs/20261008-170305-174993-astra_direct-general_pickup-l1/controller)。


控制异常：`{"error": "Traceback (most recent call last):\n  File \"/path/to/robot-agent-eval/source-snapshots/astra_policy/hybrid_rollout/robodojo/skill/run.py\", line 425, in main\n    worker = CodexPolicy(args.output/'codex_workspace', args.codex, method=args.evaluation_method)\n             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/path/to/robot-agent-eval/source-snapshots/astra_policy/hybrid_rollout/robodojo/skill/run.py\", line 176, in __init__\n    response = self.transport.request('thread/start', dict(\n               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File \"/path/to/robot-agent-eval/source-snapshots/astra_policy/hybrid_rollout/robodojo/skill/transport.py\", line 91, in request\n    raise RuntimeError(f\"Codex RPC {method} failed: {response['error']}\")\nRuntimeError: Codex RPC thread/start failed: {'code': -32603, 'message': 'error creating thread: failed to load AGENTS.md instructions for environment `local`: fs sandbox helper failed with status exit status: 1: bwrap: execvp /path/to/robot-agent-eval/secrets/codex-homes/20261008-170305-174993-astra_direct-general_pickup-l1/tmp/arg0/codex-arg069CDl7/codex-linux-sandbox: Permission denied'}\n", "controller_version": "recoverable_tool_input_v1", "episode_id": null, "step_id": 0, "counters": {}, "completed": false}`。

原始异常链（含清理阶段；先发生的异常不能被后来的 EOF 掩盖）：`["RuntimeError: Codex RPC thread/start failed: {'code': -32603, 'message': 'error creating thread: failed to load AGENTS.md instructions for environment `local`: fs sandbox helper failed with status exit status: 1: bwrap: execvp /path/to/robot-agent-eval/secrets/codex-homes/20261008-170305-174993-astra_direct-general_pickup-l1/tmp/arg0/codex-arg069CDl7/codex-linux-sandbox: Permission denied'}"]`。

没有该格式的动作决策记录；不能据此断言没有原生控制步。请以原生日志及具体方法记录为准。

### 20261008-170459-975772-astra_direct-general_pickup-l1

原生结果：成功；模型等待累计 822.49s；整次启动/执行/退出 909.22s。
模型提交请求 25 次，已结束记录 25 次；用量完整性：False。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261008-170459-975772-astra_direct-general_pickup-l1/index.json)；[控制目录](../../runs/20261008-170459-975772-astra_direct-general_pickup-l1/controller)。

[原生判分记录](../../runs/20261008-170459-975772-astra_direct-general_pickup-l1/sim/evaluation_outcome.json)。
[三视角录像](../../runs/20261008-170459-975772-astra_direct-general_pickup-l1/sim/sensors.mp4)（按仿真时间播放）。

控制异常：`{"error": "Traceback (most recent call last):\n  File \"/path/to/robot-agent-eval/source-snapshots/astra_policy/hybrid_rollout/robodojo/skill/run.py\", line 433, in main\n    worker.run(rollout)\n  File \"/path/to/robot-agent-eval/source-snapshots/astra_policy/hybrid_rollout/robodojo/skill/run.py\", line 281, in run\n    raise RuntimeError('Configured total-token budget reached; stopping this episode')\nRuntimeError: Configured total-token budget reached; stopping this episode\n", "controller_version": "recoverable_tool_input_v1", "episode_id": "2d194c2a8fbc442fa772d1404d7067e2", "step_id": 71, "counters": {"student_steps": 0, "edited_steps": 0, "recovery_steps": 0, "predictions": 0, "gpt_joint_steps": 0, "gpt_eef_steps": 71}, "completed": false}`。

原始异常链（含清理阶段；先发生的异常不能被后来的 EOF 掩盖）：`["RuntimeError: Configured total-token budget reached; stopping this episode"]`。

| 顺序 | 来源/阶段 | 控制步 | 公开动作理由 |
|---:|---|---|---|
| 1 | gpt_eef | 0 → 5 | The shovel shaft is ahead and slightly left of the right gripper. Advance the open right gripper and begin pitching downward. |
| 2 | gpt_eef | 5 → 10 | The right gripper is still behind the shaft. Continue the open approach and downward pitch while checking measured motion. |
| 3 | gpt_eef | 10 → 15 | The shovel remains stationary; the right wrist has risen during approach. Bring it forward and lower while continuing downward orientation. |
| 4 | gpt_eef | 15 → 20 | The narrow shaft is visible between the open fingertips. Advance the wrist and increase downward pitch to prepare an overhead shaft grasp. |
| 5 | gpt_eef | 20 → 25 | Continue rotating the right gripper downward above the visible shaft with fingers open. |
| 6 | gpt_eef | 25 → 30 | The open gripper remains above the shovel without contact. Continue forward and pitch toward a vertical approach. |
| 7 | gpt_eef | 30 → 35 | The wrist view places the shovel shaft to the right of the finger opening. Shift right while increasing downward pitch. |
| 8 | gpt_eef | 35 → 40 | The lateral correction brought the shaft closer to the center of the opening. Continue toward a downward grasp and lower slightly. |
| 9 | gpt_eef | 40 → 45 | The shaft is centered in the wrist view. Move forward to compensate for the final downward rotation and lower toward the shaft. |
| 10 | gpt_eef | 45 → 50 | The shaft is aligned between the fingers. Finish the vertical orientation and lower the open gripper toward the shaft. |
| 11 | gpt_eef | 50 → 54 | The vertical gripper straddles the shaft. Lower a small amount to place the pads alongside it before closing. |
| 12 | gpt_eef | 54 → 59 | The shaft lies between the pads and downward motion has stopped at contact height. Close the right gripper around the shaft. |
| 13 | gpt_eef | 59 → 64 | The fingers have closed around the shaft and centered it. Begin a vertical lift while maintaining the grasp. |
| 14 | gpt_eef | 64 → 69 | The shovel has risen with the closed gripper. Continue the vertical lift toward the required 10 cm height. |
| 15 | gpt_eef | 69 → 71 | The shovel remains held above the table. Raise another 4.5 cm to exceed the requested 10 cm lift despite its slight tilt. |

### 20261008-175803-426113-pi05_only-general_pickup-l1

原生结果：失败；模型等待累计 0.00s；整次启动/执行/退出 188.19s。
模型提交请求 0 次，已结束记录 0 次；用量完整性：True。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261008-175803-426113-pi05_only-general_pickup-l1/index.json)；[控制目录](../../runs/20261008-175803-426113-pi05_only-general_pickup-l1/controller)。

[原生判分记录](../../runs/20261008-175803-426113-pi05_only-general_pickup-l1/sim/evaluation_outcome.json)。
[三视角录像](../../runs/20261008-175803-426113-pi05_only-general_pickup-l1/sim/sensors.mp4)（按仿真时间播放）。

没有该格式的动作决策记录；不能据此断言没有原生控制步。请以原生日志及具体方法记录为准。

### 20261008-180207-968322-astra_hybrid-general_pickup-l1

原生结果：成功；模型等待累计 437.04s；整次启动/执行/退出 578.01s。
模型提交请求 16 次，已结束记录 16 次；用量完整性：True。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261008-180207-968322-astra_hybrid-general_pickup-l1/index.json)；[控制目录](../../runs/20261008-180207-968322-astra_hybrid-general_pickup-l1/controller)。

[原生判分记录](../../runs/20261008-180207-968322-astra_hybrid-general_pickup-l1/sim/evaluation_outcome.json)。
[三视角录像](../../runs/20261008-180207-968322-astra_hybrid-general_pickup-l1/sim/sensors.mp4)（按仿真时间播放）。

| 顺序 | 来源/阶段 | 控制步 | 公开动作理由 |
|---:|---|---|---|
| 1 | gpt_eef | 0 → 5 | The shovel is beside the right arm, while the proposal approaches the left-side hairbrush. Begin a bounded right-arm approach with the gripper open. |
| 2 | student | 5 → 20 | The fresh proposal now approaches the visible shovel with the right gripper open. Hand control back for the approach. |
| 3 | student | 20 → 35 | The open right gripper is aligned over the shovel. Continue the approach and descent before closing. |
| 4 | student | 35 → 50 | Close around the centered shovel shaft and begin a short lift to check whether it is held. |
| 5 | student | 50 → 55 | Continue the initial upward motion while keeping the shovel gripped, then inspect its clearance. |
| 6 | student | 55 → 58 | The shovel moved upward with the gripper. Continue the next short upward segment toward the required lift height. |

### 20261011-175055-152063-astra_react_skill-general_pickup-l1

原生结果：成功；模型等待累计 503.04s；整次启动/执行/退出 593.59s。
模型提交请求 26 次，已结束记录 26 次；用量完整性：True。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261011-175055-152063-astra_react_skill-general_pickup-l1/index.json)；[控制目录](../../runs/20261011-175055-152063-astra_react_skill-general_pickup-l1/controller)。

[原生判分记录](../../runs/20261011-175055-152063-astra_react_skill-general_pickup-l1/sim/evaluation_outcome.json)。
[三视角录像](../../runs/20261011-175055-152063-astra_react_skill-general_pickup-l1/sim/sensors.mp4)（按仿真时间播放）。

| 请求用途 | 次数 | 等待(s) | 输入token | 缓存输入 | 输出token |
|---|---:|---:|---:|---:|---:|
| planner / action selection | 26 | 503.08 | 89,887 | 0 | 12,437 |

| 顺序 | 来源/阶段 | 控制步 | 公开动作理由 |
|---:|---|---|---|
| 1 | approach | 0 → 5 | The lavender shovel is in front of the right arm; its narrow shaft between the D-shaped grip and blade is unobstructed in the right wrist view. Both fingers are open. Expected: Advance the right gripper toward the shaft with clearance while beginning to tilt the fingers downward. |
| 2 | approach | 5 → 10 | The shovel shaft remains clear between the blade and D-grip. The right hand moved only slightly toward it; the fingers are still open and largely forward-facing. Expected: Bring the open fingers farther over the narrow shaft while increasing their downward tilt. |
| 3 | approach | 10 → 15 | The lavender shaft remains unobstructed between the D-grip and blade. The right fingers are open but still nearly horizontal; the head view places the hand slightly to the right of the shovel. Expected: Advance above the shaft and shift slightly inward while tilting the fingers downward, preserving clearance. |
| 4 | approach | 15 → 20 | The lavender shaft is visible between the D-grip and blade. The open fingers are still forward-facing, with the blade nearer than the selected shaft region; measured link6 remains at z=0.922 m. Expected: Advance the open fingers toward the narrower shaft while adding downward tilt and maintaining clearance. |
| 5 | align | 20 → 25 | The shovel remains flat, with its narrow shaft visible beside the right finger in the wrist view. The open hand is still shallowly tilted; measured link6 height is 0.927 m. Expected: Advance the open fingers toward the shaft and increase downward tilt without descending into the shovel. |
| 6 | align | 25 → 30 | The wrist view shows the lavender shaft on the right side of the open finger gap, close to the right finger. The shovel is still flat; measured hand tilt is about 20 degrees and link6 height is 0.931 m. Expected: Shift the open hand toward the shaft and increase downward tilt while maintaining height. |
| 7 | align | 30 → 35 | The lavender shaft is clearly visible, but remains right of the open finger-gap center in the wrist view. The shovel is still flat, and measured hand pitch is about 29 degrees. Expected: Bring the open finger gap farther over the shaft while increasing downward orientation with clearance. |
| 8 | align | 35 → 40 | The narrow lavender shaft is now inside the open finger gap, slightly right of center in the wrist view. The shovel remains flat; measured right-hand pitch is 40 degrees and link6 height is 0.937 m. Expected: Improve shaft centering and turn the open fingers farther downward while preserving approach clearance. |
| 9 | align | 40 → 45 | The lavender shaft is centered between the open fingers in the right wrist view. The shovel remains flat on the table; measured hand pitch is 50.9 degrees and link6 height is 0.940 m. Expected: Turn the open fingers farther downward while maintaining the current hand position and clearance. |
| 10 | align | 45 → 50 | The shovel remains flat. Its shaft is visible between the open fingers, slightly left of the wrist-view center; measured hand pitch is 61.7 degrees, so the approach is still tilted. Expected: Bring the fingers closer to a downward approach while holding link6 position and leaving the gripper open. |
| 11 | align | 50 → 55 | Right wrist view shows the blade filling the lower gap and the shaft above and left of center. The shovel remains flat; measured pitch is 73.3 degrees, short of a downward approach. Expected: Bring the open fingers closer to vertical and shift the approach toward the narrow shaft rather than the blade. |
| 12 | align | 55 → 60 | The right wrist view is dominated by the shovel blade; the narrow shaft exits toward the upper-left rather than crossing the finger gap. The hand is nearly downward at 85.2 degrees pitch, and the gripper remains open. Expected: Shift the open, downward-facing gripper toward the narrow shaft while maintaining height. |
| 13 | align | 60 → 65 | The right wrist view shows the broad blade between the open fingers, with the narrower shaft extending upward slightly left of center. The shovel is still flat and the hand is nearly downward. Expected: Move the open gripper farther toward the narrow shaft, keeping height and orientation unchanged. |
| 14 | align | 65 → 70 | The narrow neck is now visible between the finger edges, with the blade immediately below. The shovel has also shifted slightly in the head view despite the open gripper, suggesting contact during alignment. Expected: Increase clearance while moving the open fingers farther toward the narrow shaft, away from the blade. |
| 15 | align | 70 → 75 | The right wrist view shows the narrow shaft above the blade, centered between the open fingers but with the blade still occupying the lower closing area. The shovel remains on the table after the clearance lift. Expected: Move the open gripper farther along the shaft toward the handle, keeping the current clearance above the table. |
| 16 | descend | 75 → 80 | The right wrist view now shows the narrow shaft between the open finger paths, with the broad blade below the closing region. The shovel remains flat on the table. Expected: Lower the open fingers slightly around the shaft without moving the shovel sideways. |
| 17 | close | 80 → 85 | The narrow lavender shaft is centered between the open fingers in the right wrist view, with the blade below the closing region. The shovel has not visibly shifted during the small descent. Expected: Close the fingers across the narrow shaft while holding the wrist stationary. |
| 18 | test_lift | 85 → 90 | The right wrist view shows both fingers closed against opposite sides of the narrow lavender shaft. The blade remains near the table; contact alone does not verify a hold. Expected: Raise the closed gripper 1.5 cm to test whether the shovel moves with it. |
| 19 | test_lift | 90 → 95 | The measured hand rose from z=0.9564 to 0.9714 m, but the blade remains close to its previous tabletop position. The shaft is still between the fingers in the wrist view; visible co-motion is not yet clear. Expected: Make a second small upward test with the fingers closed to distinguish a secure hold from sliding along the shaft. |
| 20 | recover | 95 → 100 | The hand has risen about 3 cm since closing, but the shovel blade remains at the same tabletop location in both head views. The closed fingertips do not show a secure hold. Expected: Reopen the gripper at the already-raised pose to clear the failed grasp without dragging the shovel. |
| 21 | descend | 100 → 105 | The reopened right fingers straddle the lavender shaft in the wrist view. The shovel remains on the table; the previous close at link6 z≈0.9564 m was too shallow to produce visible co-motion. Expected: Lower the open gripper 3.5 cm, slightly below the failed closing height, while preserving the shaft alignment. |
| 22 | descend | 105 → 110 | The right hand reached z=0.9514 m. The lavender shaft remains between the open finger paths in the wrist view, but this is only 5 mm below the failed closing height; the shovel still rests on the table. Expected: Lower the open fingers another 1 cm to improve contact depth around the shaft without lateral dragging. |
| 23 | close | 110 → 115 | The right hand is at z=0.9414 m, 1.5 cm below the failed closing height. The wrist view shows the narrow lavender shaft centered between the open fingers; the shovel still rests on the table. Expected: Close across the shaft at the deeper contact height without lateral movement. |
| 24 | test_lift | 115 → 120 | The right wrist view shows the lavender shaft between the inward fingers after closing. The shovel blade remains near its table position, so a hold is not yet verified. Measured link6 z is 0.9416 m. Expected: Raise the closed gripper 2 cm to test whether the shovel follows without slipping. |
| 25 | lift | 120 → 125 | The hand rose from z≈0.9416 to 0.9614 m. The shovel blade moved with the gripper in the head view, and its shaft remains captured between the fingers in the wrist view, supporting a successful test lift. Expected: Raise the held shovel another 4.5 cm while maintaining its orientation and closed grip. |
| 26 | lift | 125 → 130 | Right link6 is now at z=1.0060 m, about 6.4 cm above its pre-lift height. The shovel has moved upward with the hand in the head view, and the lavender shaft remains between the fingers in the wrist view. Expected: Raise the held shovel another 4.5 cm, targeting about 10.9 cm total measured rise with a small clearance margin. |

### 20261011-204241-426801-rpent_astra-general_pickup-l1

原生结果：未完成/未知；模型等待累计 0.00s；整次启动/执行/退出 342.28s。
模型提交请求 0 次，已结束记录 0 次；用量完整性：False。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261011-204241-426801-rpent_astra-general_pickup-l1/index.json)；[控制目录](../../runs/20261011-204241-426801-rpent_astra-general_pickup-l1/controller)。

[三视角录像](../../runs/20261011-204241-426801-rpent_astra-general_pickup-l1/sim/sensors.mp4)（按仿真时间播放）。

控制异常：`{"error_type": "AttributeError", "error": "'PublicEnv' object has no attribute 'get_status'"}`。

没有该格式的动作决策记录；不能据此断言没有原生控制步。请以原生日志及具体方法记录为准。

### 20261011-204604-277539-gap_astra-general_pickup-l1

原生结果：未完成/未知；模型等待累计 363.73s；整次启动/执行/退出 581.12s。
模型提交请求 16 次，已结束记录 16 次；用量完整性：True。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261011-204604-277539-gap_astra-general_pickup-l1/index.json)；[控制目录](../../runs/20261011-204604-277539-gap_astra-general_pickup-l1/controller)。

[三视角录像](../../runs/20261011-204604-277539-gap_astra-general_pickup-l1/sim/sensors.mp4)（按仿真时间播放）。
输入/skill 来源：`{"framework": "GaP", "skill_library": "/path/to/robot-agent-eval/source-snapshots/gap_skills", "prior_custom_shovel_skill": false, "system_sources": ["gap/agent/prompts", "gap/agent/prompt_assembler.py"], "transport_adapter": "Chat-shaped internal provider mapped to Astra Responses", "sam3_available": false, "robot_context": "Dual ARX X5, 200 control steps; no hidden object coordinates", "checkpoint_condition": "GaP semantic checkpoints unavailable without world_snapshot; native outcome evaluated externally"}`。
[完整来源及skill库文件身份](../../runs/20261011-204604-277539-gap_astra-general_pickup-l1/controller/text_provenance.json)。

控制异常：`{"error_type": "EOFError", "error": "RPC connection closed"}`。

原始异常链（含清理阶段；先发生的异常不能被后来的 EOF 掩盖）：`["RuntimeError: graph generation failed: 1 residual validation error(s): [error] subgraphs.grasp_and_lift_shovel: subgraph names skill 'grasping-linear-feature' but no script node runs one of its canonical scripts (['axis_aware_grasp_pose.py', 'axis_grasp_top_down.py']) (SK2)", "EOFError: RPC connection closed"]`。

[生成的执行图](../../runs/20261011-204604-277539-gap_astra-general_pickup-l1/controller/generated_graph/task_00/workflow.json)；所选原库技能：{"perceive_shovel_handle": "perceiving-object-parts", "grasp_and_lift_shovel": "grasping-linear-feature"}。

图阶段计时：`{"graph_generation_attempt": {"elapsed_s": 364.3414478850318}}`。

| 请求用途 | 次数 | 等待(s) | 输入token | 缓存输入 | 输出token |
|---|---:|---:|---:|---:|---:|
| GaP graph generation | 16 | 363.76 | 169,748 | 21,504 | 10,269 |

没有该格式的动作决策记录；不能据此断言没有原生控制步。请以原生日志及具体方法记录为准。

### 20261011-204734-813398-rpent_astra-general_pickup-l1

原生结果：未完成/未知；模型等待累计 0.00s；整次启动/执行/退出 73.74s。
模型提交请求 0 次，已结束记录 0 次；用量完整性：False。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261011-204734-813398-rpent_astra-general_pickup-l1/index.json)；[控制目录](../../runs/20261011-204734-813398-rpent_astra-general_pickup-l1/controller)。


没有该格式的动作决策记录；不能据此断言没有原生控制步。请以原生日志及具体方法记录为准。

### 20261011-210259-128093-phyagentos_custom_astra-general_pickup-l1

原生结果：未完成/未知；模型等待累计 351.59s；整次启动/执行/退出 441.88s。
模型提交请求 20 次，已结束记录 20 次；用量完整性：True。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261011-210259-128093-phyagentos_custom_astra-general_pickup-l1/index.json)；[控制目录](../../runs/20261011-210259-128093-phyagentos_custom_astra-general_pickup-l1/controller)。

[三视角录像](../../runs/20261011-210259-128093-phyagentos_custom_astra-general_pickup-l1/sim/sensors.mp4)（按仿真时间播放）。
输入/skill 来源：`{"framework": "PhyAgentOS-core", "skill_name": "phyagentos-shovel-pickup", "skill_source": "/path/to/robot-agent-eval/harness/skills/phyagentos-shovel-pickup/SKILL.md", "skill_sha256": "e5bb08c3fa8a0fe53ff76b5d67caf5f119724db14818dbecd6b5ee133c24b360", "official_skill": false, "prior_custom_shovel_skill": false, "custom_skill_derivation": "robodojo-shovel-pickup", "system_sources": ["PhyAgentOS/agent/context.py", "PhyAgentOS/agent/skills.py", "PhyAgentOS/verification/service.py"], "manifest_adapter": "Released profile required_tools moved to run-local manifest root; local transport profile replaces Dora launch", "retained": ["AgentLoop", "SkillActivationManager", "ForgeSkillBindingResolver", "AgentTaskCoordinator", "ForgeTaskVerifier verdict validation", "BridgeState (official condition)"], "adaptations": ["Responses provider", "local HTTP Gateway execution", "public native evidence collector", "in-process verifier transport"], "sam3_available": false, "vla_available": false}`。
[完整来源及skill库文件身份](../../runs/20261011-210259-128093-phyagentos_custom_astra-general_pickup-l1/controller/text_provenance.json)。

实际激活的 skill：`[{"version": "skill_activation_v2", "activation_id": "activation_a230c6e1406c4cb5", "skill_name": "phyagentos-shovel-pickup", "role": "primary", "source": "workspace", "content_sha256": "e5bb08c3fa8a0fe53ff76b5d67caf5f119724db14818dbecd6b5ee133c24b360", "skill_version": "0.1.0", "binding_candidate_id": "candidate_5f187c88823fd7ac2494", "activated_at": "2026-10-11T13:04:13.144769Z"}]`。

| 请求用途 | 次数 | 等待(s) | 输入token | 缓存输入 | 输出token |
|---|---:|---:|---:|---:|---:|
| planner / action selection | 17 | 143.67 | 179,356 | 12,800 | 2,769 |
| Phy image analysis | 3 | 207.97 | 1,327 | 0 | 5,720 |

实际控制段（只列产生控制步的动作；坐标为模型指令，非物体真值）：

| 控制步 | 做法 | 动作/修正 | 模型公开依据 |
|---|---|---|---|
| 0 → 5 | approach | {"arm": "right", "translation_m": [-0.025, 0.035, -0.02], "rotation_xyz_deg": [-18, 0, 0], "gripper": "open", "control_steps": 5} | Initial head and right-wrist images identify straight lavender shaft below D grip; target is left/forward of right palm in head view. |

| 顺序 | 工具/事件 | 控制步 | 时间(s) | 实际参数（前240字；完整见JSON） |
|---:|---|---|---:|---|
| 5 | activate_skill | 0 → 0 | 0.01 | {"name": "phyagentos-shovel-pickup", "role": "primary"} |
| 8 | forge_tool_context | 0 → 0 | 0.00 | {"tool_id": "robot.observe"} |
| 13 | forge_task_create | 0 → 0 | 0.03 | {"activation_id": "activation_a230c6e1406c4cb5", "task_description": "Pick up the lavender plastic shovel by 10 cm in the existing frozen general_pickup episode (task_ids=[0], init_state_ids=[1], num_runs=1, seed=0, max_steps=200). Do not r |
| 18 | forge_tool_query | 0 → 0 | 0.54 | {"tool_id": "robot.observe", "arguments": {}, "task_id": "task_bb1f2d7a82cc4b3b"} |
| 21 | forge_tool_context | 0 → 0 | 0.00 | {"tool_id": "robot.delta_action"} |
| 22 | image | 0 → 0 | 58.71 | {"image_path": "/path/to/robot-agent-eval/runs/20261011-210259-128093-phyagentos_custom_astra-general_pickup-l1/controller/sensors/forge-0001/cam_head.png", "mode": "vision", "text": "Locate the lavender plastic shovel and describe h |
| 23 | image | 0 → 0 | 85.82 | {"image_path": "/path/to/robot-agent-eval/runs/20261011-210259-128093-phyagentos_custom_astra-general_pickup-l1/controller/sensors/forge-0001/cam_right_wrist.png", "mode": "vision", "text": "Describe shovel handle relative to right g |
| 26 | custom_delta_action | 0 → 5 | — | {"stage": "approach", "evidence": "Initial head and right-wrist images identify straight lavender shaft below D grip; target is left/forward of right palm in head view.", "expected_effect": "Move right open gripper toward shaft while beginn |
| 28 | forge_tool_start_action | 0 → 5 | 4.96 | {"tool_id": "robot.delta_action", "task_id": "task_bb1f2d7a82cc4b3b", "arguments": {"stage": "approach", "evidence": "Initial head and right-wrist images identify straight lavender shaft below D grip; target is left/forward of right palm in |
| 30 | forge_tool_action_result | 5 → 5 | 0.03 | {"invocation_id": "inv_e9e48a5bc33146f2a9d5c4f945efbecc", "task_id": "task_bb1f2d7a82cc4b3b"} |
| 31 | image | 5 → 5 | 63.46 | {"image_path": "/path/to/robot-agent-eval/runs/20261011-210259-128093-phyagentos_custom_astra-general_pickup-l1/controller/sensors/forge-0004/cam_head.png", "mode": "vision", "text": "Assess right gripper pose relative to lavender sh |
| 34 | forge_tool_start_action | 5 → 5 | 0.50 | {"tool_id": "robot.delta_action", "task_id": "task_bb1f2d7a82cc4b3b", "arguments": {"stage": "approach", "evidence": "Head view shows fingertips near shaft in projection but forward-facing. Measured EE moved only to (0.2843,-0.3412,0.9158). |
| 35 | forge_task_get | 5 → 5 | 0.00 | {"task_id": "task_bb1f2d7a82cc4b3b"} |
| 38 | forge_tool_context | 5 → 5 | 0.00 | {"tool_id": "robot.observe"} |
| 42 | forge_tool_query | 5 → 5 | 0.05 | {"tool_id": "robot.observe", "arguments": {}, "task_id": "task_bb1f2d7a82cc4b3b"} |
| 43 | forge_task_cancel | 5 → 5 | 0.03 | {"task_id": "task_bb1f2d7a82cc4b3b", "reason": "Robot action and observation RPC connection closed; bridge requests reset, which is prohibited for this frozen episode. No further motion commands; cancel unresolved actions. Grasp and lift un |
| 45 | forge_tool_action_status | 5 → 5 | 0.03 | {"invocation_id": "inv_e9e48a5bc33146f2a9d5c4f945efbecc", "task_id": "task_bb1f2d7a82cc4b3b"} |

### 20261011-212157-619323-rpent_astra-general_pickup-l1

原生结果：成功；模型等待累计 36.09s；整次启动/执行/退出 313.29s。
模型提交请求 4 次，已结束记录 4 次；用量完整性：True。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261011-212157-619323-rpent_astra-general_pickup-l1/index.json)；[控制目录](../../runs/20261011-212157-619323-rpent_astra-general_pickup-l1/controller)。

[原生判分记录](../../runs/20261011-212157-619323-rpent_astra-general_pickup-l1/sim/evaluation_outcome.json)。
[三视角录像](../../runs/20261011-212157-619323-rpent_astra-general_pickup-l1/sim/sensors.mp4)（按仿真时间播放）。
输入/skill 来源：`{"framework": "RPent", "system_sources": ["robots/robodojo/prompts/system.py", "rpent/prompt/common.py"], "user_source": "robots/robodojo/prompts/user.py", "skills_used": [], "prior_custom_shovel_skill": false, "memory_root": "/path/to/robot-agent-eval/source-snapshots/rpent/memory/robodojo", "memory_available": false, "sam3_available": true, "vla_available": true, "provider_adapter": "new Responses planner; native RPent toolkit retained"}`。
[完整来源及skill库文件身份](../../runs/20261011-212157-619323-rpent_astra-general_pickup-l1/controller/text_provenance.json)。

| 请求用途 | 次数 | 等待(s) | 输入token | 缓存输入 | 输出token |
|---|---:|---:|---:|---:|---:|
| planner / action selection | 4 | 36.13 | 16,151 | 0 | 286 |

| 顺序 | 工具/事件 | 控制步 | 时间(s) | 实际参数（前240字；完整见JSON） |
|---:|---|---|---:|---|
| 1 | view_env_state | 0 → 0 | 0.00 | {} |
| 2 | segment | 0 → 0 | 0.87 | {"camera": "cam_head", "text_prompt": "the lavender plastic shovel"} |
| 3 | back_project | 0 → 0 | 0.00 | {"camera": "cam_head", "row": 239, "col": 478} |
| 4 | pi0_pick | 0 → 157 | 135.12 | {"arm": "right", "max_chunks": 10} |

### 20261011-212848-178623-rpent_astra-general_pickup-l1

原生结果：失败；模型等待累计 34.10s；整次启动/执行/退出 353.19s。
模型提交请求 4 次，已结束记录 4 次；用量完整性：True。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261011-212848-178623-rpent_astra-general_pickup-l1/index.json)；[控制目录](../../runs/20261011-212848-178623-rpent_astra-general_pickup-l1/controller)。

[原生判分记录](../../runs/20261011-212848-178623-rpent_astra-general_pickup-l1/sim/evaluation_outcome.json)。
[三视角录像](../../runs/20261011-212848-178623-rpent_astra-general_pickup-l1/sim/sensors.mp4)（按仿真时间播放）。
输入/skill 来源：`{"framework": "RPent", "system_sources": ["robots/robodojo/prompts/system.py", "rpent/prompt/common.py"], "user_source": "robots/robodojo/prompts/user.py", "skills_used": [], "prior_custom_shovel_skill": false, "memory_root": "/path/to/robot-agent-eval/source-snapshots/rpent/memory/robodojo", "memory_available": false, "sam3_available": true, "vla_available": true, "provider_adapter": "new Responses planner; native RPent toolkit retained"}`。
[完整来源及skill库文件身份](../../runs/20261011-212848-178623-rpent_astra-general_pickup-l1/controller/text_provenance.json)。

| 请求用途 | 次数 | 等待(s) | 输入token | 缓存输入 | 输出token |
|---|---:|---:|---:|---:|---:|
| planner / action selection | 4 | 34.14 | 18,340 | 0 | 265 |

| 顺序 | 工具/事件 | 控制步 | 时间(s) | 实际参数（前240字；完整见JSON） |
|---:|---|---|---:|---|
| 1 | view_env_state | 0 → 0 | 0.00 | {} |
| 2 | segment | 0 → 0 | 0.85 | {"camera": "cam_head", "text_prompt": "the lavender plastic shovel"} |
| 3 | back_project | 0 → 0 | 0.00 | {"camera": "cam_head", "row": 239, "col": 478} |
| 4 | pi0_pick | 0 → 200 | 197.86 | {"arm": "right", "max_chunks": 5} |

### 20261011-213452-358159-gap_astra-general_pickup-l1

原生结果：未完成/未知；模型等待累计 74.64s；整次启动/执行/退出 128.79s。
模型提交请求 6 次，已结束记录 6 次；用量完整性：True。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261011-213452-358159-gap_astra-general_pickup-l1/index.json)；[控制目录](../../runs/20261011-213452-358159-gap_astra-general_pickup-l1/controller)。

[原生判分记录](../../runs/20261011-213452-358159-gap_astra-general_pickup-l1/sim/evaluation_outcome.json)。
[三视角录像](../../runs/20261011-213452-358159-gap_astra-general_pickup-l1/sim/sensors.mp4)（按仿真时间播放）。
输入/skill 来源：`{"framework": "GaP", "skill_library": "/path/to/robot-agent-eval/source-snapshots/gap_skills", "prior_custom_shovel_skill": false, "system_sources": ["gap/agent/prompts", "gap/agent/prompt_assembler.py"], "transport_adapter": "Planner and VLM bundle providers mapped to the same accounted Astra Responses", "sam3_available": true, "robot_context": "Dual ARX X5, 200 control steps; no hidden object coordinates", "checkpoint_condition": "GaP semantic checkpoints unavailable without world_snapshot; native outcome evaluated externally"}`。
[完整来源及skill库文件身份](../../runs/20261011-213452-358159-gap_astra-general_pickup-l1/controller/text_provenance.json)。

控制异常：`{"error_type": "RuntimeError", "error": "graph generation failed: tool-use loop exceeded 6 rounds without a final response"}`。

原始异常链（含清理阶段；先发生的异常不能被后来的 EOF 掩盖）：`["RuntimeError: tool-use loop exceeded 6 rounds without a final response", "RuntimeError: graph generation failed: tool-use loop exceeded 6 rounds without a final response"]`。

图阶段计时：`{"graph_generation_attempt": {"elapsed_s": 76.98379796603695}}`。

| 请求用途 | 次数 | 等待(s) | 输入token | 缓存输入 | 输出token |
|---|---:|---:|---:|---:|---:|
| GaP graph generation | 6 | 74.65 | 94,766 | 0 | 1,651 |

没有该格式的动作决策记录；不能据此断言没有原生控制步。请以原生日志及具体方法记录为准。

### 20261011-213947-111735-gap_astra-general_pickup-l1

原生结果：未完成/未知；模型等待累计 581.34s；整次启动/执行/退出 633.11s。
模型提交请求 18 次，已结束记录 18 次；用量完整性：False。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261011-213947-111735-gap_astra-general_pickup-l1/index.json)；[控制目录](../../runs/20261011-213947-111735-gap_astra-general_pickup-l1/controller)。

[三视角录像](../../runs/20261011-213947-111735-gap_astra-general_pickup-l1/sim/sensors.mp4)（按仿真时间播放）。
输入/skill 来源：`{"framework": "GaP", "skill_library": "/path/to/robot-agent-eval/source-snapshots/gap_skills", "prior_custom_shovel_skill": false, "system_sources": ["gap/agent/prompts", "gap/agent/prompt_assembler.py"], "transport_adapter": "Planner and VLM bundle providers mapped to the same accounted Astra Responses", "sam3_available": true, "robot_context": "Dual ARX X5, 200 control steps; no hidden object coordinates", "checkpoint_condition": "GaP semantic checkpoints unavailable without world_snapshot; native outcome evaluated externally", "codegen_max_tool_rounds": 12, "codegen_original_default_rounds": 6}`。
[完整来源及skill库文件身份](../../runs/20261011-213947-111735-gap_astra-general_pickup-l1/controller/text_provenance.json)。

控制异常：`{"error_type": "RuntimeError", "error": "graph generation failed: Model transport failed: RemoteDisconnected"}`。

模型请求错误（保留等待时间；缺失用量未知）：`[{"call": 18, "started_monotonic": 789584.199221772, "elapsed_s": 180.0995837500086, "status": null, "usage": null, "error": "timed out", "error_type": "TimeoutError", "http_status": null}]`。

原始异常链（含清理阶段；先发生的异常不能被后来的 EOF 掩盖）：`["RuntimeError: Model transport failed: RemoteDisconnected", "RuntimeError: graph generation failed: Model transport failed: RemoteDisconnected"]`。

图阶段计时：`{"graph_generation_attempt": {"elapsed_s": 583.7086091360543}}`。

| 请求用途 | 次数 | 等待(s) | 输入token | 缓存输入 | 输出token |
|---|---:|---:|---:|---:|---:|
| GaP graph generation | 17 | 401.27 | 222,851 | 15,104 | 9,563 |

| 顺序 | 工具/事件 | 控制步 | 时间(s) | 实际参数（前240字；完整见JSON） |
|---:|---|---|---:|---|
| 1 | native_rpc_error | 0 → 0 | — | null |

### 20261011-215326-741991-gap_astra-general_pickup-l1

原生结果：未完成/未知；模型等待累计 468.76s；整次启动/执行/退出 521.27s。
模型提交请求 17 次，已结束记录 17 次；用量完整性：True。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261011-215326-741991-gap_astra-general_pickup-l1/index.json)；[控制目录](../../runs/20261011-215326-741991-gap_astra-general_pickup-l1/controller)。

[三视角录像](../../runs/20261011-215326-741991-gap_astra-general_pickup-l1/sim/sensors.mp4)（按仿真时间播放）。
输入/skill 来源：`{"framework": "GaP", "skill_library": "/path/to/robot-agent-eval/source-snapshots/gap_skills", "prior_custom_shovel_skill": false, "system_sources": ["gap/agent/prompts", "gap/agent/prompt_assembler.py"], "transport_adapter": "Planner and VLM bundle providers mapped to the same accounted Astra Responses", "sam3_available": true, "robot_context": "Dual ARX X5, 200 control steps; no hidden object coordinates", "checkpoint_condition": "GaP semantic checkpoints unavailable without world_snapshot; native outcome evaluated externally", "codegen_max_tool_rounds": 12, "codegen_original_default_rounds": 6, "interface_fixes": ["Dispatch target name positional-only; tool arguments preserved", "Motion-skill codegen catalogs expose connector solve_ik and grasp_frame; original documents/scripts unchanged"]}`。
[完整来源及skill库文件身份](../../runs/20261011-215326-741991-gap_astra-general_pickup-l1/controller/text_provenance.json)。

控制异常：`{"error_type": "RuntimeError", "error": "tool bundle 'geometry': failed to start its server (ToolClientError: [tool-bundle:geometry] subprocess unreachable on eof: returncode=2)"}`。

原始异常链（含清理阶段；先发生的异常不能被后来的 EOF 掩盖）：`["RuntimeError: tool bundle 'geometry': failed to start its server (ToolClientError: [tool-bundle:geometry] subprocess unreachable on eof: returncode=2)"]`。

[生成的执行图](../../runs/20261011-215326-741991-gap_astra-general_pickup-l1/controller/generated_graph/task_00/workflow.json)；所选原库技能：{"perceive_shovel_handle": "perceiving-object-parts", "grasp_and_lift_shovel": "grasping-linear-feature"}。

图阶段计时：`{"graph_generation_attempt": {"elapsed_s": 471.47978528100066}, "graph_generation": {"elapsed_s": 471.4797927639447, "path": "/path/to/robot-agent-eval/runs/20261011-215326-741991-gap_astra-general_pickup-l1/controller/generated_graph/task_00"}, "graph_execution": {"elapsed_s": 0.26593286299612373, "success": false, "error": "tool bundle 'geometry': failed to start its server (ToolClientError: [tool-bundle:geometry] subprocess unreachable on eof: returncode=2)", "graph_path": "/path/to/robot-agent-eval/runs/20261011-215326-741991-gap_astra-general_pickup-l1/controller/generated_graph/task_00", "result": "ExecutionResult(success=False, exit_status=None, outputs={}, trace_path=None, checkpoint_results=[], error=ToolBundleStartupError(\"tool bundle 'geometry': failed to start its server (ToolClientError: [tool-bundle:geometry] subprocess unreachable on eof: returncode=2)\"), duration_s=0.14861626992933452, latency=None)"}}`。

| 请求用途 | 次数 | 等待(s) | 输入token | 缓存输入 | 输出token |
|---|---:|---:|---:|---:|---:|
| GaP graph generation | 17 | 468.78 | 203,193 | 40,576 | 12,880 |

| 顺序 | 工具/事件 | 控制步 | 时间(s) | 实际参数（前240字；完整见JSON） |
|---:|---|---|---:|---|
| 1 | native_rpc_error | 0 → 0 | — | null |

### 20261011-220521-421225-gap_astra-general_pickup-l1

原生结果：未完成/未知；模型等待累计 0.00s；整次启动/执行/退出 58.54s。
模型提交请求 0 次，已结束记录 0 次；用量完整性：False。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261011-220521-421225-gap_astra-general_pickup-l1/index.json)；[控制目录](../../runs/20261011-220521-421225-gap_astra-general_pickup-l1/controller)。

[原生判分记录](../../runs/20261011-220521-421225-gap_astra-general_pickup-l1/sim/evaluation_outcome.json)。
[三视角录像](../../runs/20261011-220521-421225-gap_astra-general_pickup-l1/sim/sensors.mp4)（按仿真时间播放）。
输入/skill 来源：`{"framework": "GaP", "skill_library": "/path/to/robot-agent-eval/source-snapshots/gap_skills", "prior_custom_shovel_skill": false, "system_sources": ["gap/agent/prompts", "gap/agent/prompt_assembler.py"], "transport_adapter": "Planner and VLM bundle providers mapped to the same accounted Astra Responses", "sam3_available": true, "robot_context": "Dual ARX X5, 200 control steps; no hidden object coordinates", "checkpoint_condition": "GaP semantic checkpoints unavailable without world_snapshot; native outcome evaluated externally", "codegen_max_tool_rounds": 12, "codegen_original_default_rounds": 6, "interface_fixes": ["Dispatch target name positional-only; tool arguments preserved", "Motion-skill codegen catalogs expose connector solve_ik and grasp_frame; original documents/scripts unchanged"]}`。
[完整来源及skill库文件身份](../../runs/20261011-220521-421225-gap_astra-general_pickup-l1/controller/text_provenance.json)。

控制异常：`{"error_type": "RuntimeError", "error": "workflow terminated at end node 'abort' (failure); first node error -- perceive_shovel_handle.observe: Node 'perceive_shovel_handle.observe' failed: OSError: [Errno 9] Bad file descriptor"}`。

原始异常链（含清理阶段；先发生的异常不能被后来的 EOF 掩盖）：`["RuntimeError: workflow terminated at end node 'abort' (failure); first node error -- perceive_shovel_handle.observe: Node 'perceive_shovel_handle.observe' failed: OSError: [Errno 9] Bad file descriptor"]`。

[生成的执行图](../../runs/20261011-220521-421225-gap_astra-general_pickup-l1/controller/generated_graph/task_00/workflow.json)；所选原库技能：{"perceive_shovel_handle": "perceiving-object-parts", "grasp_and_lift_shovel": "grasping-linear-feature"}。

图阶段计时：`{"graph_generation_attempt": {"elapsed_s": 2.647450587945059}, "graph_generation": {"elapsed_s": 2.6474553470034152, "path": "/path/to/robot-agent-eval/runs/20261011-220521-421225-gap_astra-general_pickup-l1/controller/generated_graph/task_00", "reused": true}, "graph_reuse": {"origin": "/path/to/robot-agent-eval/runs/20261011-215326-741991-gap_astra-general_pickup-l1/controller/generated_graph/task_00", "workflow_sha256": "c96b7d673f7c4e0f0a4b8b43ae784040577d7dbca117cf2152532e0ed6987210", "prior_generation_record": "/path/to/robot-agent-eval/runs/20261011-215326-741991-gap_astra-general_pickup-l1/controller/graph_generation.json", "condition": "Reuse after tool-transport repair; prior generation cost remains separate, not free"}, "graph_execution": {"elapsed_s": 0.2728259179275483, "success": false, "error": "workflow terminated at end node 'abort' (failure); first node error -- perceive_shovel_handle.observe: Node 'perceive_shovel_handle.observe' failed: OSError: [Errno 9] Bad file descriptor", "graph_path": "/path/to/robot-agent-eval/runs/20261011-220521-421225-gap_astra-general_pickup-l1/controller/generated_graph/task_00", "result": "ExecutionResult(success=False, exit_status='failure', outputs={'perceive_shovel_handle': {}}, trace_path=PosixPath('/path/to/robot-agent-eval/runs/20261011-220521-421225-gap_astra-general_pickup-l1/controller/graph_trace'), checkpoint_results=[], error=PipelineError(\"workflow terminated at end node 'abort' (failure); first node error -- perceive_shovel_handle.observe: Node 'perceive_shovel_handle.observe' failed: OSError: [Errno 9] Bad file descriptor\"), duration_s=0.16243830195162445, latency=None)"}}`。

| 图节点 | 状态 | 时间(ms) | 失败原因 |
|---|---|---:|---|
| perceive_shovel_handle | pending | 0.00 |  |
| grasp_and_lift_shovel | pending | 0.00 |  |
| done | pending | 0.00 |  |
| abort | pending | 0.00 |  |
| perceive_shovel_handle.observe | error | 144.50 | Node 'perceive_shovel_handle.observe' failed: OSError: [Errno 9] Bad file descriptor |
| perceive_shovel_handle.perceive_handle | pending | 0.00 |  |
| perceive_shovel_handle.found | pending | 0.00 |  |
| grasp_and_lift_shovel.fit_axis | pending | 0.00 |  |
| grasp_and_lift_shovel.compute_grasp | pending | 0.00 |  |
| grasp_and_lift_shovel.select_arm | pending | 0.00 |  |
| grasp_and_lift_shovel.open | pending | 0.00 |  |
| grasp_and_lift_shovel.pregrasp | pending | 0.00 |  |
| grasp_and_lift_shovel.descend | pending | 0.00 |  |
| grasp_and_lift_shovel.observe | pending | 0.00 |  |
| grasp_and_lift_shovel.close | pending | 0.00 |  |
| grasp_and_lift_shovel.lift | pending | 0.00 |  |
| grasp_and_lift_shovel.grasped | pending | 0.00 |  |

| 顺序 | 工具/事件 | 控制步 | 时间(s) | 实际参数（前240字；完整见JSON） |
|---:|---|---|---:|---|
| 1 | native_rpc_error | 0 → 0 | — | null |
| 2 | native_rpc_error | 0 → 0 | — | null |

### 20261011-221044-073562-gap_astra-general_pickup-l1

原生结果：未完成/未知；模型等待累计 17.51s；整次启动/执行/退出 100.40s。
模型提交请求 2 次，已结束记录 2 次；用量完整性：True。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261011-221044-073562-gap_astra-general_pickup-l1/index.json)；[控制目录](../../runs/20261011-221044-073562-gap_astra-general_pickup-l1/controller)。

[原生判分记录](../../runs/20261011-221044-073562-gap_astra-general_pickup-l1/sim/evaluation_outcome.json)。
[三视角录像](../../runs/20261011-221044-073562-gap_astra-general_pickup-l1/sim/sensors.mp4)（按仿真时间播放）。
输入/skill 来源：`{"framework": "GaP", "skill_library": "/path/to/robot-agent-eval/source-snapshots/gap_skills", "prior_custom_shovel_skill": false, "system_sources": ["gap/agent/prompts", "gap/agent/prompt_assembler.py"], "transport_adapter": "Planner and VLM bundle providers mapped to the same accounted Astra Responses", "sam3_available": true, "robot_context": "Dual ARX X5, 200 control steps; no hidden object coordinates", "checkpoint_condition": "GaP semantic checkpoints unavailable without world_snapshot; native outcome evaluated externally", "codegen_max_tool_rounds": 12, "codegen_original_default_rounds": 6, "interface_fixes": ["Dispatch target name positional-only; tool arguments preserved", "Motion-skill codegen catalogs expose connector solve_ik and grasp_frame; original documents/scripts unchanged"]}`。
[完整来源及skill库文件身份](../../runs/20261011-221044-073562-gap_astra-general_pickup-l1/controller/text_provenance.json)。

控制异常：`{"error_type": "RuntimeError", "error": "workflow terminated at end node 'abort' (failure); first node error -- grasp_and_lift_shovel.select_arm: Node 'grasp_and_lift_shovel.select_arm' failed: KeyError: 'joints'"}`。

原始异常链（含清理阶段；先发生的异常不能被后来的 EOF 掩盖）：`["RuntimeError: workflow terminated at end node 'abort' (failure); first node error -- grasp_and_lift_shovel.select_arm: Node 'grasp_and_lift_shovel.select_arm' failed: KeyError: 'joints'"]`。

[生成的执行图](../../runs/20261011-221044-073562-gap_astra-general_pickup-l1/controller/generated_graph/task_00/workflow.json)；所选原库技能：{"perceive_shovel_handle": "perceiving-object-parts", "grasp_and_lift_shovel": "grasping-linear-feature"}。

图阶段计时：`{"graph_generation_attempt": {"elapsed_s": 2.6554594580084085}, "graph_generation": {"elapsed_s": 2.6554641670081764, "path": "/path/to/robot-agent-eval/runs/20261011-221044-073562-gap_astra-general_pickup-l1/controller/generated_graph/task_00", "reused": true}, "graph_reuse": {"origin": "/path/to/robot-agent-eval/runs/20261011-215326-741991-gap_astra-general_pickup-l1/controller/generated_graph/task_00", "workflow_sha256": "c96b7d673f7c4e0f0a4b8b43ae784040577d7dbca117cf2152532e0ed6987210", "prior_generation_record": "/path/to/robot-agent-eval/runs/20261011-215326-741991-gap_astra-general_pickup-l1/controller/graph_generation.json", "condition": "Reuse after tool-transport repair; prior generation cost remains separate, not free"}, "graph_execution": {"elapsed_s": 42.08054968796205, "success": false, "error": "workflow terminated at end node 'abort' (failure); first node error -- grasp_and_lift_shovel.select_arm: Node 'grasp_and_lift_shovel.select_arm' failed: KeyError: 'joints'", "graph_path": "/path/to/robot-agent-eval/runs/20261011-221044-073562-gap_astra-general_pickup-l1/controller/generated_graph/task_00", "result": "ExecutionResult(success=False, exit_status='failure', outputs={'perceive_shovel_handle': {'target_cloud': {'points': array([[ 0.34165105, -0.03807239,  0.79872215],\n       [ 0.34310567, -0.03885284,  0.7997908 ],\n       [ 0.34457302, -0.03960981,  0.8008273 ],\n       ...,\n       [ 0.32181305, -0.16077358,  0.77960753],\n       [ 0.3223036 , -0.1607    ,  0.7794748 ],\n       [ 0.32279775, -0.16061243,  0.7793168 ]], dtype=float32)}}, 'grasp_and_lift_shovel': {'grasp_pose': {'position': {'x': 0.3237060468296018, 'y': -0.1327957181881249, 'z': 0.7806158787846131}, 'rotation': {'w': 0.00453194591276262, 'x': 0.7015241904848888, 'y': 0.7126163613551076, 'z': 0.004603602912080359}}, 'pregrasp_pose': {'position': {'x': 0.3221558682026205, 'y': -0.13282003812457893, 'z': 0.9006058631781664}, 'rotation': {'w': 0.00453194591276262, 'x': 0.7015241904848888, 'y': 0.7126163613551076, 'z': 0.004603602912080359}}, 'approach_axis': {'x': 0.012918155224844198, 'y': 0.00020266613711677112, 'z': -0.9999165366129433}}}, trace_path=PosixPath('/path/to/robot-agent-eval/runs/20261011-221044-073562-gap_astra-general_pickup-l1/controller/graph_trace'), checkpoint_results=[], error=PipelineError(\"workflow terminated at end node 'abort' (failure); first node error -- grasp_and_lift_shovel.select_arm: Node 'grasp_and_lift_shovel.select_arm' failed: KeyError: 'joints'\"), duration_s=41.96965684997849, latency=None)"}}`。

| 请求用途 | 次数 | 等待(s) | 输入token | 缓存输入 | 输出token |
|---|---:|---:|---:|---:|---:|
| GaP runtime vision | 2 | 17.53 | 9,746 | 3,968 | 126 |

| 图节点 | 状态 | 时间(ms) | 失败原因 |
|---|---|---:|---|
| perceive_shovel_handle | pending | 0.00 |  |
| grasp_and_lift_shovel | pending | 0.00 |  |
| done | pending | 0.00 |  |
| abort | pending | 0.00 |  |
| perceive_shovel_handle.observe | ok | 723.08 |  |
| perceive_shovel_handle.perceive_handle | ok | 39242.85 |  |
| perceive_shovel_handle.found | pending | 0.00 |  |
| grasp_and_lift_shovel.fit_axis | ok | 6.56 |  |
| grasp_and_lift_shovel.compute_grasp | ok | 1.64 |  |
| grasp_and_lift_shovel.select_arm | error | 1807.41 | Node 'grasp_and_lift_shovel.select_arm' failed: KeyError: 'joints' |
| grasp_and_lift_shovel.open | pending | 0.00 |  |
| grasp_and_lift_shovel.pregrasp | pending | 0.00 |  |
| grasp_and_lift_shovel.descend | pending | 0.00 |  |
| grasp_and_lift_shovel.observe | pending | 0.00 |  |
| grasp_and_lift_shovel.close | pending | 0.00 |  |
| grasp_and_lift_shovel.lift | pending | 0.00 |  |
| grasp_and_lift_shovel.grasped | pending | 0.00 |  |

没有该格式的动作决策记录；不能据此断言没有原生控制步。请以原生日志及具体方法记录为准。

### 20261011-221746-476840-phyagentos_official_astra-general_pickup-l1

原生结果：失败；模型等待累计 639.88s；整次启动/执行/退出 1011.96s。
模型提交请求 56 次，已结束记录 56 次；用量完整性：True。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261011-221746-476840-phyagentos_official_astra-general_pickup-l1/index.json)；[控制目录](../../runs/20261011-221746-476840-phyagentos_official_astra-general_pickup-l1/controller)。

[原生判分记录](../../runs/20261011-221746-476840-phyagentos_official_astra-general_pickup-l1/sim/evaluation_outcome.json)。
[三视角录像](../../runs/20261011-221746-476840-phyagentos_official_astra-general_pickup-l1/sim/sensors.mp4)（按仿真时间播放）。
输入/skill 来源：`{"framework": "PhyAgentOS-core", "skill_name": "robodojo", "skill_source": "/path/to/robot-agent-eval/runtime-sources/phyagentos-robodojo-skill/SKILL.md", "skill_sha256": "4d1aca7ff006e1b0e6a2cc5e8d3403db88086dd85f6449fc322a6a30c718643c", "official_skill": true, "prior_custom_shovel_skill": false, "custom_skill_derivation": null, "system_sources": ["PhyAgentOS/agent/context.py", "PhyAgentOS/agent/skills.py", "PhyAgentOS/verification/service.py"], "manifest_adapter": "Released profile required_tools moved to run-local manifest root; local transport profile replaces Dora launch", "retained": ["AgentLoop", "SkillActivationManager", "ForgeSkillBindingResolver", "AgentTaskCoordinator", "ForgeTaskVerifier verdict validation", "BridgeState (official condition)"], "adaptations": ["Responses provider", "local HTTP Gateway execution", "public native evidence collector", "in-process verifier transport"], "sam3_available": false, "vla_available": true}`。
[完整来源及skill库文件身份](../../runs/20261011-221746-476840-phyagentos_official_astra-general_pickup-l1/controller/text_provenance.json)。

实际激活的 skill：`[{"version": "skill_activation_v2", "activation_id": "activation_8c7e680f903a4f75", "skill_name": "robodojo", "role": "primary", "source": "workspace", "content_sha256": "4d1aca7ff006e1b0e6a2cc5e8d3403db88086dd85f6449fc322a6a30c718643c", "skill_version": "0.2.1", "binding_candidate_id": "candidate_95a1a2f25f3355a435d9", "activated_at": "2026-10-11T14:19:32.156607Z"}, {"version": "skill_activation_v2", "activation_id": "activation_d8f2de29a0574223", "skill_name": "image", "role": "supporting", "source": "builtin", "content_sha256": "e374b69396aecc4cd3f65a3c5b1cf9d6d6f7f5af793c8637baeea2b907271d32", "skill_version": null, "binding_candidate_id": null, "activated_at": "2026-10-11T14:20:16.044274Z"}]`。

工具返回的错误（模型可能继续运行，不等于进程崩溃）：

- 第 200 步，forge_task_finalize：Error executing forge_task_finalize: cannot finalize while task-owned Action/Session invocation(s) are non-terminal: inv_fb4e09a6d4fb4fc1ad2bf0cf6f440398  [Analyze the error above and try a different approach.]

| 请求用途 | 次数 | 等待(s) | 输入token | 缓存输入 | 输出token |
|---|---:|---:|---:|---:|---:|
| planner / action selection | 48 | 377.09 | 1,323,009 | 222,080 | 6,392 |
| Phy image analysis | 8 | 262.96 | 3,404 | 0 | 6,059 |

实际控制段（只列产生控制步的动作；坐标为模型指令，非物体真值）：

| 控制步 | 做法 | 动作/修正 | 模型公开依据 |
|---|---|---|---|
| 0 → 10 | vla.decide | {"mode": "student", "steps": 10} | Begin bounded approach at C0; current-episode images unavailable before the first step. |
| 10 → 20 | vla.decide | {"mode": "student", "steps": 10} | Early approach at step 10; wrist view shows open gripper offset from shovel, with no grasp or collision established. Continue bounded native alignment; joint-axis geometry is unavailable, so avoid speculative edits. |
| 20 → 30 | vla.decide | {"mode": "student", "steps": 10} | Step 20: open gripper remains in approach; images show no definite collision or grasp. Continue native alignment for one bounded segment. |
| 30 → 40 | vla.decide | {"mode": "edit", "steps": 10, "edit": {"left_gripper": "open"}} | At step 30, left wrist shows hairbrush handle between open jaws and head view locates lavender shovel elsewhere. Prevent wrong-object closure while allowing native policy repositioning. |
| 40 → 50 | vla.decide | {"mode": "edit", "steps": 10, "edit": {"left_gripper": "open"}} | Step 40: left wrist still centered on hairbrush, while right wrist shows shovel only in projection without confirmed contact. Continue native repositioning with left closure inhibited to avoid wrong-object grasp. |
| 50 → 200 | vla.set_mode | {"mode": "student"} |  |

| 顺序 | 工具/事件 | 控制步 | 时间(s) | 实际参数（前240字；完整见JSON） |
|---:|---|---|---:|---|
| 17 | activate_skill | 0 → 0 | 0.04 | {"name": "robodojo", "role": "primary"} |
| 34 | forge_task_create | 0 → 0 | 0.05 | {"activation_id": "activation_8c7e680f903a4f75", "task_description": "Pick up the lavender plastic shovel by 10 cm in the single frozen general_pickup episode, task_ids=[0], init_state_ids=[1], num_runs=1, seed=0, max_steps=200, using gpt6_ |
| 37 | forge_tool_context | 0 → 0 | 0.00 | {"tool_id": "bench.describe"} |
| 42 | forge_tool_query | 0 → 0 | 0.08 | {"tool_id": "bench.describe", "arguments": {}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 45 | forge_tool_context | 0 → 0 | 0.00 | {"tool_id": "vla.get_status"} |
| 48 | forge_tool_context | 0 → 0 | 0.00 | {"tool_id": "vla.decide"} |
| 51 | forge_tool_context | 0 → 0 | 0.00 | {"tool_id": "vision.get_frame"} |
| 56 | forge_tool_query | 0 → 0 | 0.05 | {"tool_id": "vla.get_status", "arguments": {}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 57 | activate_skill | 0 → 0 | 0.00 | {"name": "image", "role": "supporting"} |
| 61 | forge_gateway_error | 0 → 0 | 0.01 | {"arguments": {"mode": "student", "steps": 10, "reason": "C0 initial checkpoint of already-running frozen episode. No current episode images yet; permit bounded native policy approach without speculative joint edits.", "assessment": {"phase |
| 62 | forge_tool_query | 0 → 0 | 0.06 | {"tool_id": "vla.decide", "arguments": {"mode": "student", "steps": 10, "reason": "C0 initial checkpoint of already-running frozen episode. No current episode images yet; permit bounded native policy approach without speculative joint edits |
| 65 | forge_tool_context | 0 → 0 | 0.00 | {"tool_id": "bench.run"} |
| 69 | forge_tool_start_action | 0 → 0 | 0.81 | {"tool_id": "bench.run", "arguments": {"task_ids": [0], "init_state_ids": [1], "num_runs": 1, "seed": 0, "max_steps": 200}, "task_id": "task_a1fa7cc8cfcf4204", "timeout_ms": 1800000} |
| 74 | forge_tool_query | 0 → 10 | 42.41 | {"tool_id": "vla.decide", "arguments": {"mode": "student", "steps": 10, "reason": "Begin bounded approach at C0; current-episode images unavailable before the first step."}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 79 | forge_tool_query | 10 → 10 | 0.05 | {"tool_id": "vla.get_status", "arguments": {}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 84 | forge_tool_query | 10 → 10 | 0.68 | {"tool_id": "vision.get_frame", "arguments": {"max_age_ms": 60000}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 85 | image | 10 → 10 | 48.24 | {"image_path": "/path/to/robot-agent-eval/runs/20261011-221746-476840-phyagentos_official_astra-general_pickup-l1/controller/sensors/forge-0002/cam_head.png", "mode": "vision", "text": "Inspect the robot's current approach to pick up |
| 88 | forge_tool_context | 10 → 10 | 0.00 | {"tool_id": "vision.get_frame_left_wrist"} |
| 93 | forge_tool_query | 10 → 10 | 0.69 | {"tool_id": "vision.get_frame_left_wrist", "arguments": {"max_age_ms": 60000}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 94 | image | 10 → 10 | 31.80 | {"image_path": "/path/to/robot-agent-eval/runs/20261011-221746-476840-phyagentos_official_astra-general_pickup-l1/controller/sensors/forge-0003/cam_left_wrist.png", "mode": "vision", "text": "Assess the lavender plastic shovel pickup |
| 99 | forge_tool_query | 10 → 20 | 11.91 | {"tool_id": "vla.decide", "arguments": {"mode": "student", "steps": 10, "reason": "Early approach at step 10; wrist view shows open gripper offset from shovel, with no grasp or collision established. Continue bounded native alignment; joint |
| 104 | forge_tool_query | 20 → 20 | 0.05 | {"tool_id": "vla.get_status", "arguments": {}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 109 | forge_tool_query | 20 → 20 | 0.70 | {"tool_id": "vision.get_frame", "arguments": {"max_age_ms": 60000}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 110 | image | 20 → 20 | 33.40 | {"image_path": "/path/to/robot-agent-eval/runs/20261011-221746-476840-phyagentos_official_astra-general_pickup-l1/controller/sensors/forge-0004/cam_head.png", "mode": "vision", "text": "At step 20 of lavender plastic shovel pickup: d |
| 115 | forge_tool_query | 20 → 30 | 11.87 | {"tool_id": "vla.decide", "arguments": {"mode": "student", "steps": 10, "reason": "Step 20: open gripper remains in approach; images show no definite collision or grasp. Continue native alignment for one bounded segment.", "assessment": {"p |
| 120 | forge_tool_query | 30 → 30 | 0.05 | {"tool_id": "vla.get_status", "arguments": {}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 125 | forge_tool_query | 30 → 30 | 0.70 | {"tool_id": "vision.get_frame_left_wrist", "arguments": {"max_age_ms": 60000}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 126 | image | 30 → 30 | 13.57 | {"image_path": "/path/to/robot-agent-eval/runs/20261011-221746-476840-phyagentos_official_astra-general_pickup-l1/controller/sensors/forge-0005/cam_left_wrist.png", "mode": "vision", "text": "Current step 30 left wrist camera: is the |
| 131 | forge_tool_query | 30 → 30 | 0.70 | {"tool_id": "vision.get_frame", "arguments": {"max_age_ms": 60000}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 132 | image | 30 → 30 | 49.75 | {"image_path": "/path/to/robot-agent-eval/runs/20261011-221746-476840-phyagentos_official_astra-general_pickup-l1/controller/sensors/forge-0006/cam_head.png", "mode": "vision", "text": "Describe current positions of both grippers, th |
| 137 | forge_tool_query | 30 → 40 | 11.64 | {"tool_id": "vla.decide", "arguments": {"mode": "edit", "steps": 10, "edit": {"left_gripper": "open"}, "reason": "At step 30, left wrist shows hairbrush handle between open jaws and head view locates lavender shovel elsewhere. Prevent wrong |
| 142 | forge_tool_query | 40 → 40 | 0.06 | {"tool_id": "vla.get_status", "arguments": {}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 147 | forge_tool_query | 40 → 40 | 0.70 | {"tool_id": "vision.get_frame_left_wrist", "arguments": {"max_age_ms": 60000}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 148 | image | 40 → 40 | 9.55 | {"image_path": "/path/to/robot-agent-eval/runs/20261011-221746-476840-phyagentos_official_astra-general_pickup-l1/controller/sensors/forge-0007/cam_left_wrist.png", "mode": "vision", "text": "Describe what object is between the open  |
| 151 | forge_tool_context | 40 → 40 | 0.00 | {"tool_id": "vision.get_frame_right_wrist"} |
| 156 | forge_tool_query | 40 → 40 | 0.72 | {"tool_id": "vision.get_frame_right_wrist", "arguments": {"max_age_ms": 60000}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 157 | image | 40 → 40 | 32.97 | {"image_path": "/path/to/robot-agent-eval/runs/20261011-221746-476840-phyagentos_official_astra-general_pickup-l1/controller/sensors/forge-0008/cam_right_wrist.png", "mode": "vision", "text": "Right wrist view: locate lavender shovel |
| 162 | forge_tool_query | 40 → 50 | 11.67 | {"tool_id": "vla.decide", "arguments": {"mode": "edit", "steps": 10, "edit": {"left_gripper": "open"}, "reason": "Step 40: left wrist still centered on hairbrush, while right wrist shows shovel only in projection without confirmed contact.  |
| 167 | forge_tool_query | 50 → 50 | 0.05 | {"tool_id": "vla.get_status", "arguments": {}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 170 | forge_tool_context | 50 → 50 | 0.00 | {"tool_id": "vla.set_mode"} |
| 175 | forge_tool_query | 50 → 50 | 0.68 | {"tool_id": "vision.get_frame", "arguments": {"max_age_ms": 60000}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 176 | image | 50 → 50 | 43.71 | {"image_path": "/path/to/robot-agent-eval/runs/20261011-221746-476840-phyagentos_official_astra-general_pickup-l1/controller/sensors/forge-0009/cam_head.png", "mode": "vision", "text": "At current step 50 identify target lavender sho |
| 181 | forge_tool_query | 50 → 200 | 169.13 | {"tool_id": "vla.set_mode", "arguments": {"mode": "student"}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 186 | forge_tool_query | 200 → 200 | 0.05 | {"tool_id": "vla.get_status", "arguments": {}, "task_id": "task_a1fa7cc8cfcf4204"} |
| 188 | forge_tool_action_status | 200 → 200 | 0.03 | {"invocation_id": "inv_fb4e09a6d4fb4fc1ad2bf0cf6f440398", "task_id": "task_a1fa7cc8cfcf4204"} |
| 190 | forge_tool_action_result | 200 → 200 | 0.02 | {"invocation_id": "inv_fb4e09a6d4fb4fc1ad2bf0cf6f440398", "task_id": "task_a1fa7cc8cfcf4204"} |
| 191 | forge_task_finalize | 200 → 200 | 0.00 | {"task_id": "task_a1fa7cc8cfcf4204"} |
| 192 | forge_task_get | 200 → 200 | 0.00 | {"task_id": "task_a1fa7cc8cfcf4204"} |

### 20261011-223519-789805-phyagentos_custom_astra-general_pickup-l1

原生结果：未完成/未知；模型等待累计 36.74s；整次启动/执行/退出 98.57s。
模型提交请求 7 次，已结束记录 6 次；用量完整性：False。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261011-223519-789805-phyagentos_custom_astra-general_pickup-l1/index.json)；[控制目录](../../runs/20261011-223519-789805-phyagentos_custom_astra-general_pickup-l1/controller)。

[原生判分记录](../../runs/20261011-223519-789805-phyagentos_custom_astra-general_pickup-l1/sim/evaluation_outcome.json)。
[三视角录像](../../runs/20261011-223519-789805-phyagentos_custom_astra-general_pickup-l1/sim/sensors.mp4)（按仿真时间播放）。
输入/skill 来源：`{"framework": "PhyAgentOS-core", "skill_name": "phyagentos-shovel-pickup", "skill_source": "/path/to/robot-agent-eval/harness/skills/phyagentos-shovel-pickup/SKILL.md", "skill_sha256": "e5bb08c3fa8a0fe53ff76b5d67caf5f119724db14818dbecd6b5ee133c24b360", "official_skill": false, "prior_custom_shovel_skill": false, "custom_skill_derivation": "robodojo-shovel-pickup", "system_sources": ["PhyAgentOS/agent/context.py", "PhyAgentOS/agent/skills.py", "PhyAgentOS/verification/service.py"], "manifest_adapter": "Released profile required_tools moved to run-local manifest root; local transport profile replaces Dora launch", "retained": ["AgentLoop", "SkillActivationManager", "ForgeSkillBindingResolver", "AgentTaskCoordinator", "ForgeTaskVerifier verdict validation", "BridgeState (official condition)"], "adaptations": ["Responses provider", "local HTTP Gateway execution", "public native evidence collector", "in-process verifier transport"], "sam3_available": false, "vla_available": false}`。
[完整来源及skill库文件身份](../../runs/20261011-223519-789805-phyagentos_custom_astra-general_pickup-l1/controller/text_provenance.json)。

实际激活的 skill：`[{"version": "skill_activation_v2", "activation_id": "activation_c565215610054a03", "skill_name": "phyagentos-shovel-pickup", "role": "primary", "source": "workspace", "content_sha256": "e5bb08c3fa8a0fe53ff76b5d67caf5f119724db14818dbecd6b5ee133c24b360", "skill_version": "0.1.0", "binding_candidate_id": "candidate_05eee4127a5a85ba1f7a", "activated_at": "2026-10-11T14:36:05.284186Z"}]`。

主动停止的部署条件：`{"status": "adapter_contract_error", "reason": "Stopped before robot actions to correct local Gateway status/phase receipt contract; not a robot capability trial"}`。

| 请求用途 | 次数 | 等待(s) | 输入token | 缓存输入 | 输出token |
|---|---:|---:|---:|---:|---:|
| planner / action selection | 6 | 36.75 | 34,202 | 5,888 | 520 |

| 顺序 | 工具/事件 | 控制步 | 时间(s) | 实际参数（前240字；完整见JSON） |
|---:|---|---|---:|---|
| 5 | activate_skill | 0 → 0 | 0.01 | {"name": "phyagentos-shovel-pickup", "role": "primary"} |
| 8 | forge_tool_context | 0 → 0 | 0.00 | {"tool_id": "robot.observe"} |
| 13 | forge_task_create | 0 → 0 | 0.03 | {"activation_id": "activation_c565215610054a03", "task_description": "In the single frozen general_pickup episode (task 0, initial state 1, seed 0), pick up the lavender plastic shovel and lift it by 10 cm. No reset or second batch.", "veri |
| 18 | forge_tool_query | 0 → 0 | 0.68 | {"tool_id": "robot.observe", "arguments": {}, "task_id": "task_65a457e132de44dc"} |
| 21 | forge_tool_context | 0 → 0 | 0.00 | {"tool_id": "robot.delta_action"} |

### 20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1

原生结果：未完成/未知；模型等待累计 1103.87s；整次启动/执行/退出 1216.44s。
模型提交请求 52 次，已结束记录 51 次；用量完整性：False。False 时上表 token 是已记录量，未返回用量不补零。
[文本审计](input-text/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/index.json)；[控制目录](../../runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/controller)。

[原生判分记录](../../runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/sim/evaluation_outcome.json)。
[三视角录像](../../runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/sim/sensors.mp4)（按仿真时间播放）。
输入/skill 来源：`{"framework": "PhyAgentOS-core", "skill_name": "phyagentos-shovel-pickup", "skill_source": "/path/to/robot-agent-eval/harness/skills/phyagentos-shovel-pickup/SKILL.md", "skill_sha256": "e5bb08c3fa8a0fe53ff76b5d67caf5f119724db14818dbecd6b5ee133c24b360", "official_skill": false, "prior_custom_shovel_skill": false, "custom_skill_derivation": "robodojo-shovel-pickup", "system_sources": ["PhyAgentOS/agent/context.py", "PhyAgentOS/agent/skills.py", "PhyAgentOS/verification/service.py"], "manifest_adapter": "Released profile required_tools moved to run-local manifest root; local transport profile replaces Dora launch", "retained": ["AgentLoop", "SkillActivationManager", "ForgeSkillBindingResolver", "AgentTaskCoordinator", "ForgeTaskVerifier verdict validation", "BridgeState (official condition)"], "adaptations": ["Responses provider", "local HTTP Gateway execution", "public native evidence collector", "in-process verifier transport"], "sam3_available": false, "vla_available": false}`。
[完整来源及skill库文件身份](../../runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/controller/text_provenance.json)。

实际激活的 skill：`[{"version": "skill_activation_v2", "activation_id": "activation_9bf7130673d14ded", "skill_name": "phyagentos-shovel-pickup", "role": "primary", "source": "workspace", "content_sha256": "e5bb08c3fa8a0fe53ff76b5d67caf5f119724db14818dbecd6b5ee133c24b360", "skill_version": "0.1.0", "binding_candidate_id": "candidate_55ab63a2685724c6b2d8", "activated_at": "2026-10-11T14:39:43.974757Z"}, {"version": "skill_activation_v2", "activation_id": "activation_3e99ef0e52b04890", "skill_name": "image", "role": "supporting", "source": "builtin", "content_sha256": "e374b69396aecc4cd3f65a3c5b1cf9d6d6f7f5af793c8637baeea2b907271d32", "skill_version": null, "binding_candidate_id": null, "activated_at": "2026-10-11T14:40:03.943878Z"}]`。

模型请求错误（保留等待时间；缺失用量未知）：`[{"call": 42, "started_monotonic": 793642.311956488, "elapsed_s": 51.385180543060414, "status": null, "usage": null, "error": null, "error_type": "HTTPError", "http_status": 502}]`。

| 请求用途 | 次数 | 等待(s) | 输入token | 缓存输入 | 输出token |
|---|---:|---:|---:|---:|---:|
| planner / action selection | 40 | 405.38 | 743,299 | 191,616 | 8,019 |
| Phy image analysis | 10 | 647.24 | 4,232 | 0 | 15,483 |

实际控制段（只列产生控制步的动作；坐标为模型指令，非物体真值）：

| 控制步 | 做法 | 动作/修正 | 模型公开依据 |
|---|---|---|---|
| 0 → 3 | approach | {"arm": "right", "translation_m": [0, 0.045, 0], "rotation_xyz_deg": [0, 0, 0], "gripper": "open", "control_steps": 3} | Initial head image locates shaft near (479,230), above-left of right gripper. Wrist shaft near (383,350); no contact. |
| 3 → 8 | align | {"arm": "right", "translation_m": [-0.045, 0.015, 0], "rotation_xyz_deg": [0, 0, 0], "gripper": "open", "control_steps": 5} | Wrist shaft near (384,350), about 60 px right of gap center; head target lies left of right hand. No contact. |
| 8 → 13 | align | {"arm": "right", "translation_m": [-0.015, 0, 0.015], "rotation_xyz_deg": [-20, 0, 0], "gripper": "open", "control_steps": 5} | Head fingertips midpoint (497,240), shaft (479,232). Fingers appear forward-reaching rather than top-down. |
| 13 → 18 | approach | {"arm": "right", "translation_m": [-0.01, 0.04, 0], "rotation_xyz_deg": [-20, 0, 0], "gripper": "open", "control_steps": 5} | Measured wrist orientation changed toward downward pitch; gripper remains open, z=0.93641. |
| 18 → 23 | align | {"arm": "right", "translation_m": [0.015, 0.04, 0], "rotation_xyz_deg": [-20, 0, 0], "gripper": "open", "control_steps": 5} | Head view fingertip midpoint (461,230), shaft (477,233); open gripper appears clear. Downward pitch still incomplete. |
| 23 → 28 | approach | {"arm": "right", "translation_m": [0, 0.045, 0], "rotation_xyz_deg": [-20, 0, 0], "gripper": "open", "control_steps": 5} | Measured right hand advanced to y=-0.27252, z=0.95762 with partial downward pitch; no closure. |
| 28 → 33 | align | {"arm": "right", "translation_m": [0.03, 0.03, 0], "rotation_xyz_deg": [-20, 0, 0], "gripper": "open", "control_steps": 5} | Wrist shaft x≈510 vs gap center x≈320, partly behind right jaw; substantial centering correction needed. |
| 33 → 38 | align | {"arm": "right", "translation_m": [0, 0.03, 0], "rotation_xyz_deg": [-20, 0, 0], "gripper": "open", "control_steps": 5} | Head fingertip midpoint (478,204), shaft (480,233), hand remains above target. Measured pitch is still oblique. |
| 38 → 43 | align | {"arm": "right", "translation_m": [0, 0, 0], "rotation_xyz_deg": [-19, -3, 0], "gripper": "open", "control_steps": 5} | Measured quaternion [0.63427,-0.27367,0.38998,0.60887] indicates forward finger axis tilted down but still oblique. |
| 43 → 48 | align | {"arm": "right", "translation_m": [0, 0, 0], "rotation_xyz_deg": [-20, 0, 0], "gripper": "open", "control_steps": 5} | Measured finger-forward axis is largely downward; current EE z=0.97240, fingers open. |
| 48 → 53 | align | {"arm": "right", "translation_m": [-0.02, 0, 0], "rotation_xyz_deg": [0, 0, 0], "gripper": "open", "control_steps": 5} | Wrist target (422,90), gap (320,292); head gap nearly overlaps shaft but depth unresolved. |
| 53 → 58 | align | {"arm": "right", "translation_m": [0.03, 0.04, 0], "rotation_xyz_deg": [0, 0, 0], "gripper": "open", "control_steps": 5} | A measured -20mm world-x shift moved shaft +81px; shaft now (503,90), gap (320,294). |

| 顺序 | 工具/事件 | 控制步 | 时间(s) | 实际参数（前240字；完整见JSON） |
|---:|---|---|---:|---|
| 5 | activate_skill | 0 → 0 | 0.01 | {"name": "phyagentos-shovel-pickup", "role": "primary"} |
| 8 | forge_tool_context | 0 → 0 | 0.00 | {"tool_id": "robot.observe"} |
| 13 | forge_task_create | 0 → 0 | 0.03 | {"activation_id": "activation_9bf7130673d14ded", "task_description": "Pick up the lavender plastic shovel by 10 cm in the existing frozen general_pickup episode, task_ids=[0], init_state_ids=[1], num_runs=1, seed=0, max_steps=200. Do not re |
| 18 | forge_tool_query | 0 → 0 | 0.68 | {"tool_id": "robot.observe", "arguments": {}, "task_id": "task_7856013efd1c43f7"} |
| 19 | activate_skill | 0 → 0 | 0.00 | {"name": "image", "role": "supporting"} |
| 20 | image | 0 → 0 | 48.78 | {"mode": "vision", "image_path": "/path/to/robot-agent-eval/runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/controller/sensors/forge-0001/cam_head.png", "text": "Locate the lavender plastic shovel and describe n |
| 21 | image | 0 → 0 | 74.80 | {"mode": "vision", "image_path": "/path/to/robot-agent-eval/runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/controller/sensors/forge-0001/cam_right_wrist.png", "text": "Describe the lavender shovel handle relati |
| 24 | forge_tool_context | 0 → 0 | 0.00 | {"tool_id": "robot.delta_action"} |
| 27 | custom_delta_action | 0 → 3 | — | {"stage": "approach", "evidence": "Initial head image locates shaft near (479,230), above-left of right gripper. Wrist shaft near (383,350); no contact.", "expected_effect": "Move right hand forward toward the handle while open and assess i |
| 29 | forge_tool_start_action | 0 → 3 | 4.52 | {"tool_id": "robot.delta_action", "task_id": "task_7856013efd1c43f7", "arguments": {"stage": "approach", "evidence": "Initial head image locates shaft near (479,230), above-left of right gripper. Wrist shaft near (383,350); no contact.", "e |
| 31 | forge_tool_action_result | 3 → 3 | 0.03 | {"task_id": "task_7856013efd1c43f7", "invocation_id": "inv_8f36aa9530c9456f9f5e6aa591e713d7"} |
| 32 | image | 3 → 3 | 68.61 | {"mode": "vision", "image_path": "/path/to/robot-agent-eval/runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/controller/sensors/forge-0004/cam_right_wrist.png", "text": "Locate narrow lavender shovel shaft and gr |
| 35 | custom_delta_action | 3 → 8 | — | {"stage": "align", "evidence": "Wrist shaft near (384,350), about 60 px right of gap center; head target lies left of right hand. No contact.", "expected_effect": "Shift open right hand inward toward shaft.", "next_check": "Compare head-vie |
| 37 | forge_tool_start_action | 3 → 8 | 5.67 | {"tool_id": "robot.delta_action", "task_id": "task_7856013efd1c43f7", "arguments": {"stage": "align", "evidence": "Wrist shaft near (384,350), about 60 px right of gap center; head target lies left of right hand. No contact.", "expected_eff |
| 39 | forge_tool_action_result | 8 → 8 | 0.03 | {"task_id": "task_7856013efd1c43f7", "invocation_id": "inv_964b6c7cba7349ae806f0bf9ecb10fe9"} |
| 40 | image | 8 → 8 | 101.11 | {"mode": "vision", "image_path": "/path/to/robot-agent-eval/runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/controller/sensors/forge-0006/cam_head.png", "text": "Inspect robot right gripper orientation and posit |
| 43 | custom_delta_action | 8 → 13 | — | {"stage": "align", "evidence": "Head fingertips midpoint (497,240), shaft (479,232). Fingers appear forward-reaching rather than top-down.", "expected_effect": "Begin downward wrist pitch and move slightly inward, maintaining open fingers." |
| 45 | forge_tool_start_action | 8 → 13 | 5.71 | {"tool_id": "robot.delta_action", "task_id": "task_7856013efd1c43f7", "arguments": {"stage": "align", "evidence": "Head fingertips midpoint (497,240), shaft (479,232). Fingers appear forward-reaching rather than top-down.", "expected_effect |
| 47 | forge_tool_action_result | 13 → 13 | 0.03 | {"task_id": "task_7856013efd1c43f7", "invocation_id": "inv_6636016c937c4602829770da5947f2ee"} |
| 50 | custom_delta_action | 13 → 18 | — | {"stage": "approach", "evidence": "Measured wrist orientation changed toward downward pitch; gripper remains open, z=0.93641.", "expected_effect": "Continue downward pitch and advance toward overhead handle position.", "next_check": "Inspec |
| 52 | forge_tool_start_action | 13 → 18 | 5.81 | {"tool_id": "robot.delta_action", "task_id": "task_7856013efd1c43f7", "arguments": {"stage": "approach", "evidence": "Measured wrist orientation changed toward downward pitch; gripper remains open, z=0.93641.", "expected_effect": "Continue  |
| 54 | forge_tool_action_result | 18 → 18 | 0.02 | {"task_id": "task_7856013efd1c43f7", "invocation_id": "inv_a56e75c4a309406686bc8ab4ac39f1f6"} |
| 55 | image | 18 → 18 | 134.51 | {"mode": "vision", "image_path": "/path/to/robot-agent-eval/runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/controller/sensors/forge-0010/cam_head.png", "text": "Report right gripper fingertips midpoint and lave |
| 58 | custom_delta_action | 18 → 23 | — | {"stage": "align", "evidence": "Head view fingertip midpoint (461,230), shaft (477,233); open gripper appears clear. Downward pitch still incomplete.", "expected_effect": "Advance toward overhead pose and increase downward pitch.", "next_ch |
| 60 | forge_tool_start_action | 18 → 23 | 5.94 | {"tool_id": "robot.delta_action", "task_id": "task_7856013efd1c43f7", "arguments": {"stage": "align", "evidence": "Head view fingertip midpoint (461,230), shaft (477,233); open gripper appears clear. Downward pitch still incomplete.", "expe |
| 62 | forge_tool_action_result | 23 → 23 | 0.03 | {"task_id": "task_7856013efd1c43f7", "invocation_id": "inv_9225b2a7c2874a07b7df21a5986415fb"} |
| 65 | custom_delta_action | 23 → 28 | — | {"stage": "approach", "evidence": "Measured right hand advanced to y=-0.27252, z=0.95762 with partial downward pitch; no closure.", "expected_effect": "Continue forward while rotating toward top-down grasp.", "next_check": "Inspect wrist sh |
| 67 | forge_tool_start_action | 23 → 28 | 5.88 | {"tool_id": "robot.delta_action", "task_id": "task_7856013efd1c43f7", "arguments": {"stage": "approach", "evidence": "Measured right hand advanced to y=-0.27252, z=0.95762 with partial downward pitch; no closure.", "expected_effect": "Conti |
| 69 | forge_tool_action_result | 28 → 28 | 0.03 | {"task_id": "task_7856013efd1c43f7", "invocation_id": "inv_17ac1d5ebc3e456e953c9d9f0c57b7b5"} |
| 70 | image | 28 → 28 | 53.28 | {"mode": "vision", "image_path": "/path/to/robot-agent-eval/runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/controller/sensors/forge-0014/cam_right_wrist.png", "text": "Locate lavender shovel shaft and gripper g |
| 73 | custom_delta_action | 28 → 33 | — | {"stage": "align", "evidence": "Wrist shaft x≈510 vs gap center x≈320, partly behind right jaw; substantial centering correction needed.", "expected_effect": "Shift outward and forward, increasing downward pitch while open.", "next_check":  |
| 75 | forge_tool_start_action | 28 → 33 | 5.89 | {"tool_id": "robot.delta_action", "task_id": "task_7856013efd1c43f7", "arguments": {"stage": "align", "evidence": "Wrist shaft x≈510 vs gap center x≈320, partly behind right jaw; substantial centering correction needed.", "expected_effect": |
| 77 | forge_tool_action_result | 33 → 33 | 0.03 | {"task_id": "task_7856013efd1c43f7", "invocation_id": "inv_5622cafae2da4de8b52466c2f9a04579"} |
| 78 | image | 33 → 33 | 44.90 | {"mode": "vision", "image_path": "/path/to/robot-agent-eval/runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/controller/sensors/forge-0016/cam_head.png", "text": "Give right fingertip midpoint, shovel narrow-shaf |
| 81 | custom_delta_action | 33 → 38 | — | {"stage": "align", "evidence": "Head fingertip midpoint (478,204), shaft (480,233), hand remains above target. Measured pitch is still oblique.", "expected_effect": "Increase downward pitch while advancing overhead.", "next_check": "Use mea |
| 83 | forge_tool_start_action | 33 → 38 | 5.85 | {"tool_id": "robot.delta_action", "task_id": "task_7856013efd1c43f7", "arguments": {"stage": "align", "evidence": "Head fingertip midpoint (478,204), shaft (480,233), hand remains above target. Measured pitch is still oblique.", "expected_e |
| 85 | forge_tool_action_result | 38 → 38 | 0.03 | {"task_id": "task_7856013efd1c43f7", "invocation_id": "inv_527bce195d714e618263e35855cf49c1"} |
| 88 | custom_delta_action | 38 → 43 | — | {"stage": "align", "evidence": "Measured quaternion [0.63427,-0.27367,0.38998,0.60887] indicates forward finger axis tilted down but still oblique.", "expected_effect": "Continue wrist rotation toward downward approach without translating." |
| 90 | forge_tool_start_action | 38 → 43 | 5.99 | {"tool_id": "robot.delta_action", "task_id": "task_7856013efd1c43f7", "arguments": {"stage": "align", "evidence": "Measured quaternion [0.63427,-0.27367,0.38998,0.60887] indicates forward finger axis tilted down but still oblique.", "expect |
| 92 | forge_tool_action_result | 43 → 43 | 0.03 | {"task_id": "task_7856013efd1c43f7", "invocation_id": "inv_3da8d544b34149f0bb5d4fde4415ad66"} |
| 95 | custom_delta_action | 43 → 48 | — | {"stage": "align", "evidence": "Measured finger-forward axis is largely downward; current EE z=0.97240, fingers open.", "expected_effect": "Bring approach closer to vertical.", "next_check": "Inspect shaft and gap in wrist image.", "memory" |
| 97 | forge_tool_start_action | 43 → 48 | 5.80 | {"tool_id": "robot.delta_action", "task_id": "task_7856013efd1c43f7", "arguments": {"stage": "align", "evidence": "Measured finger-forward axis is largely downward; current EE z=0.97240, fingers open.", "expected_effect": "Bring approach cl |
| 99 | forge_tool_action_result | 48 → 48 | 0.03 | {"task_id": "task_7856013efd1c43f7", "invocation_id": "inv_d7176c77fb2a4e3d83f6c74fb2f529c3"} |
| 100 | image | 48 → 48 | 51.39 | {"mode": "vision", "image_path": "/path/to/robot-agent-eval/runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/controller/sensors/forge-0022/cam_right_wrist.png", "text": "Locate lavender shaft target and jaw gap c |
| 101 | image | 48 → 48 | 45.01 | {"mode": "vision", "image_path": "/path/to/robot-agent-eval/runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/controller/sensors/forge-0022/cam_head.png", "text": "Locate right gripper fingertips, gap midpoint, an |
| 102 | image | 48 → 48 | 32.20 | {"mode": "vision", "image_path": "/path/to/robot-agent-eval/runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/controller/sensors/forge-0022/cam_right_wrist.png", "text": "Give pixel coordinates of lavender narrow  |
| 105 | custom_delta_action | 48 → 53 | — | {"stage": "align", "evidence": "Wrist target (422,90), gap (320,292); head gap nearly overlaps shaft but depth unresolved.", "expected_effect": "Probe inward horizontal correction and observe target shift without descent.", "next_check": "C |
| 107 | forge_tool_start_action | 48 → 53 | 5.77 | {"tool_id": "robot.delta_action", "task_id": "task_7856013efd1c43f7", "arguments": {"stage": "align", "evidence": "Wrist target (422,90), gap (320,292); head gap nearly overlaps shaft but depth unresolved.", "expected_effect": "Probe inward |
| 109 | forge_tool_action_result | 53 → 53 | 0.05 | {"task_id": "task_7856013efd1c43f7", "invocation_id": "inv_9ef0fa33bfe449cd8b680dd38408cee1"} |
| 110 | image | 53 → 53 | 44.09 | {"mode": "vision", "image_path": "/path/to/robot-agent-eval/runs/20261011-223857-872072-phyagentos_custom_astra-general_pickup-l1/controller/sensors/forge-0024/cam_right_wrist.png", "text": "After world x=-20mm only, locate narrow sh |
| 113 | custom_delta_action | 53 → 58 | — | {"stage": "align", "evidence": "A measured -20mm world-x shift moved shaft +81px; shaft now (503,90), gap (320,294).", "expected_effect": "Reduce rightward and upward shaft offset with outward/forward correction.", "next_check": "Inspect wr |
| 115 | forge_tool_start_action | 53 → 58 | 5.82 | {"tool_id": "robot.delta_action", "task_id": "task_7856013efd1c43f7", "arguments": {"stage": "align", "evidence": "A measured -20mm world-x shift moved shaft +81px; shaft now (503,90), gap (320,294).", "expected_effect": "Reduce rightward a |
