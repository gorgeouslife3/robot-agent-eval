# Astra hybrid：新增感知与实际任务执行

本轮所有任务动作仍由真实Astra hybrid决策：接受π0.5提议、edit或EEF接管。感知只提供观测，没有本地自主抓取序列，没有历史Astra语义种子回放。
所有组使用同一开发铲子layout1，420秒控制进程预算。尚无放置、未见布局或实机评估。

## 主要任务对照

每个条件最近一次实际进入任务的尝试如下；基础设施中断与全部重试在下一表保留。本表每条件只列最近一次尝试，SAM+原始深度还有一次受上游错误影响的任务尝试；单布局重复有限，不能把这张表当成功率或因果收益。

| 新增感知 | 实际执行步 | 420秒结果 |
|---|---:|---|
| H0 无新增感知 | 54 | 预算内未完成 |
| H1 原始深度 | 47 | 预算内未完成 |
| H2 SAM3 + 原始深度 | 57 | 原生成功；预算时间按历史回执核验，见下文 |
| H3 SAM3 + LingBot深度 | 56 | 原生成功；预算时间按历史回执核验，见下文 |

感知证据确实进入加感知组的Astra请求；本轮主要被用于确认目标侧，尚未证明精确几何改变了接近/抓取。速度瓶颈仍是Astra等待，单次H3成功不能归因于LingBot。

## 逐次结果

| 条件 | 原生控制步 | student/edit/eef决策数 | Astra提交/结束 | 已记录等待(s) | 控制进程含清理(s) | 状态 | 原生成功 | 严格420秒内成功 |
|---|---:|---|---:|---:|---:|---|---|---|
| [none](../../runs/20261013-191738-450408-astra_hybrid-general_pickup-l1/result.json) | 5 | 0/0/1 | 5/4 | 183.22 | 307.55 | native_transport_error | None | False |
| [none](../../runs/20261013-192945-922393-astra_hybrid-general_pickup-l1/result.json) | 0 | 0/0/1 | 4/4 | 106.11 | 162.16 | native_transport_error | None | False |
| [raw_depth](../../runs/20261013-193342-261060-astra_hybrid-general_pickup-l1/result.json) | 0 | 0/0/0 | 0/0 | 0.00 | 0.00 | infrastructure_error | None | False |
| [sam_raw_depth](../../runs/20261013-194025-900212-astra_hybrid-general_pickup-l1/result.json) | 35 | 2/0/1 | 13/13 | 343.70 | 422.77 | wall_budget | None | False |
| [sam_lingbot_depth](../../runs/20261013-194909-519422-astra_hybrid-general_pickup-l1/result.json) | 56 | 4/0/1 | 13/13 | 340.58 | 422.85 | wall_budget | True | True |
| [none](../../runs/20261013-195747-622453-astra_hybrid-general_pickup-l1/result.json) | 54 | 4/0/1 | 13/12 | 311.51 | 423.18 | wall_budget | None | False |
| [raw_depth](../../runs/20261013-200711-112809-astra_hybrid-general_pickup-l1/result.json) | 47 | 3/0/1 | 12/11 | 319.24 | 423.23 | wall_budget | None | False |
| [sam_raw_depth](../../runs/20261013-201536-472037-astra_hybrid-general_pickup-l1/result.json) | 57 | 4/0/1 | 14/13 | 317.71 | 423.02 | wall_budget | True | True |

提交/结束不一致或失败请求没有usage时，用量不完整；未结束调用的等待仅是已记录下限。没有原生结束的预算耗尽任务算预算内未完成，原生分数保持未知。首个H0尝试仿真器异常退出（-11、RPC EOF），5步后中断，归基础设施而不是抓取失败；原result保留，另存accounting_transport_revision修正汇总分类。H0重试也发生仿真器异常退出；首个H1尚未启动controller时，campaign父进程工具会话以143结束，来源未知；两个已加载的子服务已清理，0请求/0控制步，不作为任务对照样本。

SAM+LingBot达到独立原生终止成功（56步），随后保存最后RGB时被预算信号中断。最终action_000055.json已经记录terminated=true、success=true、step_id=56；其文件时间距controller命令文件写入419.493秒，后者先于controller启动。在主机时钟未跳变的条件下，这支持原生成功发生在420秒内，但余量不足1秒。这是历史文件时间的上界证据，不是精确单调时钟完成时间；不能用episode_active_wall_s=389.23秒替代。原结果不覆盖，另存accounting_budget_revision记录依据。

首次SAM+原始深度组有2次上游模型响应失败；原Codex日志明确记录“Concurrency limit exceeded for user”。两次失败等待共61.24秒并触发自动重连，尽管本机GPU试验是串行。这会挤占420秒任务预算，不能把该次35步停滞解释为SAM使Astra变慢；失败请求计入总等待，但上游未给usage，计费用量不完整。

SAM+原始深度补跑达到原生成功（57步），终止动作文件时间给出的控制进程耗时上界为395.426秒；随后Astra收尾请求被420秒截止中断。该次没有已记录的失败响应，但末次请求用量未知。同样以accounting_budget_revision保存历史文件时间核验，不能把控制器超时等同于任务失败。

首轮对照结束后，后续runner已补存controller启动单调时钟，native_server在终止动作后、保存观测前记录终止单调时钟；按同一截止计算预算成功。缺少时钟的历史截止成功须单独核验，汇总把未知预算结果单列，避免把收尾超时或超时后的完成混入成功率。该记账修复没有用于本批在线运行，不改变本批冻结实现身份。

## 感知证据是否进入Astra，以及Astra怎样决策

### 20261013-191738-450408-astra_hybrid-general_pickup-l1 / none

含perception_evidence的真实模型请求：0；完成的本地感知观测：0。[完整审计](attempts.json)。
模型失败请求：0；记录的重连事件：0；模型用量完整：False。
- response_000.json: eef, 5步；公开理由：RGB places the lavender shovel on the right, but the proposal approaches left-side objects. Move the open right gripper slightly forward and upward and begin turning downward. No perception measurement affected this decision.
### 20261013-192945-922393-astra_hybrid-general_pickup-l1 / none

含perception_evidence的真实模型请求：0；完成的本地感知观测：0。[完整审计](attempts.json)。
模型失败请求：0；记录的重连事件：0；模型用量完整：True。
- response_000.json: eef, 5步；公开理由：RGB places the lavender shovel on the right, while the proposal approaches left-side clutter and leaves the right arm stationary. Begin a bounded right-arm approach with the gripper open. No additional perception measurement was supplied.
### 20261013-193342-261060-astra_hybrid-general_pickup-l1 / raw_depth

含perception_evidence的真实模型请求：0；完成的本地感知观测：0。[完整审计](attempts.json)。
模型失败请求：0；记录的重连事件：0；模型用量完整：False。
### 20261013-194025-900212-astra_hybrid-general_pickup-l1 / sam_raw_depth

含perception_evidence的真实模型请求：11；完成的本地感知观测：4。[完整审计](attempts.json)。
模型失败请求：2；记录的重连事件：2；模型用量完整：False。
感知进程模型加载12.06秒。
- response_000.json: eef, 5步；公开理由：Begin a bounded right-arm approach and downward reorientation. Step-0 meter-scale surface measurements corroborate the right-side shovel seen in RGB but do not define the grasp target.
- response_001.json: student, 15步；公开理由：Hand control back: the new proposal approaches the correct shovel with the right arm. The step-5 surface measurement corroborates its location, while RGB establishes the handle and approach.
- response_002.json: student, 15步；公开理由：Continue the aligned approach for 15 steps and observe before closure. No object measurement is available at step 20; RGB and robot FK support this decision.
- 观测step=0：目标数1，感知0.836秒，LingBot前向—；错误=[]。[回执](../../runs/20261013-194025-900212-astra_hybrid-general_pickup-l1/controller/perception_host/0000/evidence.json)。
- 观测step=5：目标数1，感知0.536秒，LingBot前向—；错误=[]。[回执](../../runs/20261013-194025-900212-astra_hybrid-general_pickup-l1/controller/perception_host/0005/evidence.json)。
- 观测step=20：目标数0，感知0.427秒，LingBot前向—；错误=[{'stage': 'target_segmentation', 'error': 'SAM target not found: top score 0.143 is below min_score 0.200'}]。[回执](../../runs/20261013-194025-900212-astra_hybrid-general_pickup-l1/controller/perception_host/0020/evidence.json)。
- 观测step=35：目标数1，感知0.530秒，LingBot前向—；错误=[]。[回执](../../runs/20261013-194025-900212-astra_hybrid-general_pickup-l1/controller/perception_host/0035/evidence.json)。
### 20261013-194909-519422-astra_hybrid-general_pickup-l1 / sam_lingbot_depth

含perception_evidence的真实模型请求：11；完成的本地感知观测：5。[完整审计](attempts.json)。
模型失败请求：0；记录的重连事件：0；模型用量完整：True。
感知进程模型加载14.86秒。
- response_000.json: eef, 5步；公开理由：The RGB shows the target on the right, whereas the proposal selects the left-side object. Start a bounded right-arm approach and downward reorientation. Step-0 surface measurements corroborate target side only; their centroid is not used as a grasp target.
- response_001.json: student, 15步；公开理由：The new proposal now selects the visible shovel and provides an appropriate approach. Hand control back to pi05. Surface measurements did not change this decision.
- response_002.json: student, 15步；公开理由：The approach remains aligned with the visible shovel shaft. Execute the open-gripper descent and reassess before closing. The noisy surface median did not alter the motion.
- response_003.json: student, 15步；公开理由：The shaft is visibly between the approaching fingers, and the proposal closes before lifting. Execute through the initial lift to test the grasp. Perception estimates did not change the decision.
- response_004.json: student, 10步；公开理由：Continue the proposed lift while retaining the grasp, then inspect object motion. Step-50 segmentation returned no target, so no perception measurement affected this decision.
- 观测step=0：目标数1，感知0.772秒，LingBot前向0.25717188604176044；错误=[]。[回执](../../runs/20261013-194909-519422-astra_hybrid-general_pickup-l1/controller/perception_host/0000/evidence.json)。
- 观测step=5：目标数1，感知0.551秒，LingBot前向0.08033627399709076；错误=[]。[回执](../../runs/20261013-194909-519422-astra_hybrid-general_pickup-l1/controller/perception_host/0005/evidence.json)。
- 观测step=20：目标数1，感知0.546秒，LingBot前向0.08507079200353473；错误=[]。[回执](../../runs/20261013-194909-519422-astra_hybrid-general_pickup-l1/controller/perception_host/0020/evidence.json)。
- 观测step=35：目标数1，感知0.543秒，LingBot前向0.08001359098125249；错误=[]。[回执](../../runs/20261013-194909-519422-astra_hybrid-general_pickup-l1/controller/perception_host/0035/evidence.json)。
- 观测step=50：目标数0，感知0.419秒，LingBot前向0.07946384709794074；错误=[{'stage': 'target_segmentation', 'error': 'SAM target not found: top score 0.160 is below min_score 0.200'}]。[回执](../../runs/20261013-194909-519422-astra_hybrid-general_pickup-l1/controller/perception_host/0050/evidence.json)。
### 20261013-195747-622453-astra_hybrid-general_pickup-l1 / none

含perception_evidence的真实模型请求：0；完成的本地感知观测：0。[完整审计](attempts.json)。
模型失败请求：0；记录的重连事件：0；模型用量完整：False。
- response_000.json: eef, 5步；公开理由：The shovel is on the right in head and right-wrist RGB, but the proposal approaches the left-side brush area. Begin an open right-arm approach and hold the left arm. No attached perception measurement informed this correction.
- response_001.json: student, 15步；公开理由：The fresh proposal now approaches the visible shovel with the right arm and keeps the left arm at home. Hand control back for the open approach; no attached perception measurement affected this decision.
- response_002.json: student, 15步；公开理由：The right gripper is approaching the shovel shaft in RGB, and the proposal continues an open descent. No perception measurement is attached.
- response_003.json: student, 12步；公开理由：RGB shows the shaft between the open right fingers. Execute the proposed final descent and closure, then inspect contact before continuing the lift; no attached measurement affected the decision.
- response_004.json: student, 7步；公开理由：The right fingers visibly surround the shaft. Execute only the initial closed-gripper lift to test whether the shovel follows; the later lowering and release are outside this selected chunk. No attached measurement affected the decision.
### 20261013-200711-112809-astra_hybrid-general_pickup-l1 / raw_depth

含perception_evidence的真实模型请求：11；完成的本地感知观测：5。[完整审计](attempts.json)。
模型失败请求：0；记录的重连事件：0；模型用量完整：False。
感知进程模型加载0.00秒。
- response_000.json: eef, 5步；公开理由：The visible lavender shovel is on the right, but the proposal approaches left-side objects. Move the open right gripper slightly forward and orient downward; coarse depth measurements did not set this target.
- response_001.json: student, 15步；公开理由：The fresh proposal now approaches the visible right-side shovel with an open right gripper. Return control to pi05; the coarse depth grid did not alter this decision.
- response_002.json: student, 15步；公开理由：The right wrist view shows the shovel shaft between the open fingers, and the next segment descends toward it. Allow the approach; depth samples did not change the decision.
- response_003.json: student, 12步；公开理由：The shaft is visible between the fingers and the proposal lowers slightly before closing. Execute through closure, then inspect the grasp before further lifting; depth measurements did not adjust the motion.
- 观测step=0：目标数0，感知0.002秒，LingBot前向—；错误=[]。[回执](../../runs/20261013-200711-112809-astra_hybrid-general_pickup-l1/controller/perception_host/0000/evidence.json)。
- 观测step=5：目标数0，感知0.001秒，LingBot前向—；错误=[]。[回执](../../runs/20261013-200711-112809-astra_hybrid-general_pickup-l1/controller/perception_host/0005/evidence.json)。
- 观测step=20：目标数0，感知0.001秒，LingBot前向—；错误=[]。[回执](../../runs/20261013-200711-112809-astra_hybrid-general_pickup-l1/controller/perception_host/0020/evidence.json)。
- 观测step=35：目标数0，感知0.001秒，LingBot前向—；错误=[]。[回执](../../runs/20261013-200711-112809-astra_hybrid-general_pickup-l1/controller/perception_host/0035/evidence.json)。
- 观测step=47：目标数0，感知0.001秒，LingBot前向—；错误=[]。[回执](../../runs/20261013-200711-112809-astra_hybrid-general_pickup-l1/controller/perception_host/0047/evidence.json)。
### 20261013-201536-472037-astra_hybrid-general_pickup-l1 / sam_raw_depth

含perception_evidence的真实模型请求：12；完成的本地感知观测：6。[完整审计](attempts.json)。
模型失败请求：0；记录的重连事件：0；模型用量完整：False。
感知进程模型加载11.93秒。
- response_000.json: eef, 5步；公开理由：The RGB shovel is on the right, but the proposal approaches and closes the left arm on the opposite side. The matching step-0 surface measurement corroborates the side only; its centroid is not used as a grasp target. Begin a bounded open right-arm approach.
- response_001.json: student, 15步；公开理由：After the short correction, the new proposal selects the right arm and approaches the visible shovel with open fingers. Hand control back to pi05. The step-5 surface measurement agrees with the observed side but does not set the motion.
- response_002.json: student, 15步；公开理由：The right wrist view shows the shovel shaft between the open fingers' approach corridor. Continue the proposed descent and orientation before closure. The step-20 surface measurement corroborates the region but does not alter the action.
- response_003.json: student, 15步；公开理由：Current right-wrist RGB shows the shaft centered in the finger corridor. Execute the proposed closure and short initial lift to test the grasp visually. The step-35 surface estimate does not change this decision.
- response_004.json: student, 10步；公开理由：The fingers visibly enclose the shaft and the shovel has shifted upward slightly with initial lifting. Continue a short closed-gripper lift and inspect retention. The step-50 surface height estimate is consistent with small motion but is not success evidence.
- 观测step=0：目标数1，感知0.772秒，LingBot前向—；错误=[]。[回执](../../runs/20261013-201536-472037-astra_hybrid-general_pickup-l1/controller/perception_host/0000/evidence.json)。
- 观测step=5：目标数1，感知0.541秒，LingBot前向—；错误=[]。[回执](../../runs/20261013-201536-472037-astra_hybrid-general_pickup-l1/controller/perception_host/0005/evidence.json)。
- 观测step=20：目标数1，感知0.540秒，LingBot前向—；错误=[]。[回执](../../runs/20261013-201536-472037-astra_hybrid-general_pickup-l1/controller/perception_host/0020/evidence.json)。
- 观测step=35：目标数1，感知0.537秒，LingBot前向—；错误=[]。[回执](../../runs/20261013-201536-472037-astra_hybrid-general_pickup-l1/controller/perception_host/0035/evidence.json)。
- 观测step=50：目标数1，感知0.522秒，LingBot前向—；错误=[]。[回执](../../runs/20261013-201536-472037-astra_hybrid-general_pickup-l1/controller/perception_host/0050/evidence.json)。
- 观测step=57：目标数1，感知0.546秒，LingBot前向—；错误=[]。[回执](../../runs/20261013-201536-472037-astra_hybrid-general_pickup-l1/controller/perception_host/0057/evidence.json)。

这里只审计公开assessment/reason与实际response，不读取私有推理。字段出现在请求中只是“可见”的证据；决策引用和动作变化才支持它被使用，仍不等于任务成功。

## 共同条件检查

全部尝试的共同配置/共同说明/实现身份种类数：{'common_config_sha256': 1, 'common_prompt_sha256': 1, 'implementation_sha256': 2}。初次部署重试可能跨实现版本，不能将不同版本合并成功率；对照批次在campaign文件中单列。
同一campaign已结束组的共同身份种类数：{'common_config_sha256': 1, 'common_prompt_sha256': 1, 'implementation_sha256': 1}。
π0.5仍只消费原RGB/任务/proprio；新增mask、深度和几何不会进入π0.5输入。H0与所有组均host采集原始RGB-D，H0的host原始深度对Astra禁止读取。
各条件最近一次实际进入任务的对照组：['sam_raw_depth', 'sam_lingbot_depth', 'none', 'raw_depth']；共同身份种类数：{'common_config_sha256': 1, 'common_prompt_sha256': 1, 'implementation_sha256': 1}。完整重试仍在上表，不择优。共享case/seed不保证初始RGB逐位相同，初始传感器哈希在attempts.json中保留。
该批初始头部深度/标定/RGB的哈希种类数：{'cam_head_depth': 1, 'cam_head_intrinsic_matrix': 1, 'cam_head_extrinsic_matrix': 1, 'rgb': 4}。
感知RGB与同step的原Astra头部RGB来自相邻两次公开采集，期间未执行动作，但渲染不逐位一致；各帧平均通道差范围0.0578–0.3400（0–255量程）。帧版本一致不代表图片逐位相同，完整差异审计保留。

## LingBot-Depth的真实离线接入

同一公开录制帧，官方v0.5权重实际前向0.299秒；SAM文本分割目标数1。resolution_level=0，不是默认9档速度。
原生输入深度完全有效；预测与原生深度在目标mask内RMSE=2.34cm，MAE=1.54cm，p95绝对差=4.14cm。这是与干净渲染深度的比较，没有证明对真实传感器更差或更好。
第一次推理因缺少xFormers嵌套张量依赖失败，保留日志；隔离安装匹配原torch2.7的xformers0.0.30后真实推理通过。源码与1.28GB权重有固定来源与哈希，没有替换模型。
[几何差异](../hybrid-lingbot-recorded-20261013-v2/comparison_to_clean_rendered_depth.json)；[模型来源/运行身份](../hybrid-lingbot-recorded-20261013-v2/model_identity.json)。

![同一铲子裁剪：RGB、原深度、LingBot精修及深度差](../hybrid-lingbot-recorded-20261013-v2/depth-comparison.png)
两幅深度图共用色标；差值图以厘米表示，显示范围截断到±5cm。

## 同一公开帧的深度质量/缺失消融

干净渲染深度仅用于评测参考，退化推理只输入退化深度。固定随机seed=41；同一SAM mask、同一RGB。误差均对干净渲染深度计算，不是真实传感器精度或Astra任务成功率。

| 输入条件 | 档位 | 前向(s) | 目标输入覆盖 | 目标输出覆盖 | 目标输入RMSE(cm) | 目标输出RMSE(cm) | 目标缺失区输出RMSE(cm) | 目标原有效区输出RMSE(cm) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| clean | 0 | 0.264 | 100.0% | 100.0% | 0.00 | 2.34 | — | 2.34 |
| clean | 9 | 0.227 | 100.0% | 100.0% | 0.00 | 1.89 | — | 1.89 |
| random_holes_30pct | 0 | 0.074 | 69.9% | 100.0% | 0.00 | 2.36 | 2.44 | 2.33 |
| shaft_block_hole | 0 | 0.070 | 79.0% | 100.0% | 0.00 | 2.39 | 1.69 | 2.54 |
| gaussian_noise_10mm | 0 | 0.069 | 100.0% | 100.0% | 1.04 | 2.45 | — | 2.45 |
[全部区域指标与模型身份](../lingbot-depth-audit-20261013/results.json)。冷/热前向顺序不同，单次耗时不构成稳定吞吐基准。

![目标深度覆盖与误差](../lingbot-depth-audit-20261013/target-depth-audit.png)
输入误差仅统计原有效像素；空洞不是零误差。输出误差包含补全后的像素，区域不同，须结合覆盖率及缺失/原有效区分项解读。

## 当前结论与下一步

本轮为小规模真实Astra任务开发对照。只按实际完成/预算中断报告，不从少量尝试估计架构成功率。也不拿旧本地自主抓取88秒与新Astra hybrid直接比较来宣称感知改善。
SAM+LingBot组只在首段引用感知确认目标侧，后续公开理由明确说表面估计未改变决策；遮挡时SAM还会返回无目标。单次终止成功不能归因于LingBot，也没有证明泛化或420秒多次抓放。该组Astra累计等待340.58秒，LingBot热前向约0.08秒；当前速度瓶颈仍是Astra调用，仅加快感知无法解决，应继续测低层动作分块执行与事件触发Astra复核。
无上游失败响应的SAM+原始深度补跑也在57步成功，历史时间上界395.43秒；因此现有结果没有显示LingBot优于原始深度。H0/H1分别54/47步预算内未完成，这些单次差异仍混有模型响应时间、决策分块及轨迹波动，不能估计加SAM的净收益。
本轮感知进程常驻，但只在Astra获取新观测时推理，更新间隔仍跟随原工具循环；尚未测试后台持续感知和异步执行。0.08秒是前向耗时，不是当前端到端更新频率。
先核对动作确实使用感知，再对冻结的未见布局重复。优先检验理想深度/空洞/噪声分层，表示消融（叠图/结构化几何）和更新机制；随后接入单目米制模型与检测/跟踪备选，最后扩至放置、420秒多轮与实机。
[已有方法调查](../../experiments/perception-manipulation/perception-survey.zh-CN.md)；[主对照计划与命令](../../experiments/perception-manipulation/astra-hybrid-plan.zh-CN.md)。
