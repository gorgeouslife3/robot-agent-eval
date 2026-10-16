# 现有感知方法与 Astra 任务执行对照

资料核对日期：2026-10-13。以下依据官方代码仓库、README和模型发布信息；
项目宣称的效果不当作本机实验结果。本机实测另列在任务执行报告中。
抓取规划器不是感知模型，先固定 Astra hybrid 的动作能力，再改变感知输入。

## 优先调研结果

| 方法与官方来源 | 输入 → 输出 | 本任务的用途 | 需要检验的限制 | 优先级 |
|---|---|---|---|---|
| [LingBot-Depth v0.5](https://github.com/Robbyant/lingbot-depth) | RGB + 原始深度，可带内参 → 补全/精修的米制深度、点云 | 深度空洞、噪声、反光物体附近的几何修复，给 Astra 更可靠的距离证据 | 当前 `v2.py` 的 forward 明确要求 depth；不能把它当无深度相机的单目替代。补全可能捏造表面；理想仿真深度上可能无收益或变差 | 第一批 |
| [Depth Anything 3](https://github.com/ByteDance-Seed/Depth-Anything-3) | 单/多视图RGB，可带相机参数 → 深度、几何、相机等 | 无深度传感器时的几何补充；多视角一致性 | 必须区分 DA3 Main、Metric、Mono、Nested；主系列不自动等于米制深度。首选 DA3Metric-Large 检验尺度，Nested 的代价另测 | 第二批 |
| [Depth Pro](https://github.com/apple-aiml-research/ml-depth-pro) | 单幅RGB，可带焦距 → 米制深度、焦距估计 | 测细柄/边界与单目距离 | “Less Than a Second”是项目定位，不是3090实测；近距离尺度偏差、焦距/裁剪需单独测 | 第二批 |
| [UniDepth V2](https://github.com/lpiccinelli-eth/UniDepth) | RGB，可带已知相机 → 米制深度、点云、内参 | 单目尺度与相机适应性对照 | 有内参与无内参应分组；桌面近距离、遮挡与边界精度未知 | 第二批 |
| [Depth Anything V2](https://github.com/DepthAnything/Depth-Anything-V2) | RGB → 相对深度；另有 metric fine-tuned 版本 | 较轻量的深度备选，Small/Base 与大模型比较时间 | 普通相对深度输出不能直接以米反投影；metric版本仍要测试室内近距离偏差 | 第二批 |
| [MoGe / MoGe-2](https://github.com/microsoft/MoGe) | RGB → 点图/深度/FOV；MoGe-2支持米制尺度和法线 | 给 Astra 表面、主轴与放置平面信息 | 固定具体版本，不能混合相对与米制模型；估计内参不应覆盖机器人已标定内参 | 第二批 |
| [SAM 3](https://github.com/facebookresearch/sam3) | RGB/视频 + 文本、点、框 → mask与跟踪 | 由任务文字定位物体，或由 Astra 选部位后细化边界；已有本机权重 | 小目标、遮挡、类别混淆与分数阈值；mask是像素集合，不是三维位姿/抓取点；同进程BF16上下文需隔离 | 第一批 |
| [SAM 2.1](https://github.com/facebookresearch/sam2) | RGB/视频 + 点/框/mask → 分割与视频跟踪 | Astra 首次指定目标后，用视频记忆维持身份 | 不能单靠SAM2从语言确定“抓哪一个”；官方FPS基准不等于本机全闭环FPS，且在线流式接入需验证 | 动态阶段 |
| [Grounding DINO](https://github.com/IDEA-Research/GroundingDINO) + [Grounded SAM 2](https://github.com/IDEA-Research/Grounded-SAM-2) | RGB + 文本 → 开放词汇框 → mask/跟踪 | 目标与放置容器的开放词汇定位；本机已有DINO/SAM来源 | 检测框可能抓错同类物体；检测+SAM增加延迟，需要和SAM3文本分割比较 | 第一批后续 |
| [YOLO-World](https://github.com/AILab-CVC/YOLO-World) | RGB + 类别词汇 → 开放词汇检测框 | 快速初始识别、事件触发再识别 | 框不提供接触几何；需结合分割/深度，且类别描述与SAM/DINO对照一致 | 快速检测备选 |
| [CoTracker3](https://github.com/facebookresearch/co-tracker) | 视频 + 查询点 → 点轨迹、可见性 | 追踪 Astra 选中的柄部/放置点，区分手移动和目标移动 | 点跟踪不保证对象身份，不输出米制坐标；在线模型与离线模型不能混用比较延迟 | 动态阶段 |
| [DINOv3](https://github.com/facebookresearch/dinov3) | RGB → 视觉特征；附带下游分割/跟踪例程 | 目标重识别、相似物体区分、遮挡后匹配 | 裸特征模型不是即用实例分割或位姿工具，需明确下游算法与训练条件 | 身份恢复阶段 |
| [FoundationPose](https://github.com/NVlabs/FoundationPose) | RGB-D + 初始mask + mesh或参考重建 → 6D位姿、跟踪 | 已知物体精确放置、稳定检验 | 参考模型/扫描是额外先验；不能和完全未知物体条件直接合并。需衡量初始化成本 | 精确放置阶段 |
| [VGGT](https://github.com/facebookresearch/vggt)、[MASt3R](https://github.com/naver/mast3r) | 单/多视图RGB → 相机、点图、匹配等 | 多视角一致性、缺外参时重建 | 单目尺度/相机规范和跨视图外参需验证；多图全局计算未必适合每轮控制 | 场景重建备选 |
| [DepthCrafter](https://github.com/Tencent/DepthCrafter) | RGB视频 → 时间一致深度序列 | 录制视频的离线几何与时序评估 | 视频扩散推理的时间和尺度条件不同，先作离线候选，不当高频在线首选 | 离线备选 |

第一批先比较原始深度、SAM3+原始深度、SAM3+LingBot-Depth。
这三者保留相同RGB输入和已标定相机，能分开观察目标分割与深度精修的收益。
之后增加一种单目米制模型（优先DA3Metric或UniDepth V2），再根据边界精度、延迟、
显存选择Depth Pro/DA2/MoGe补充，不一次堆叠所有模型。

## LingBot-Depth的本机接入

使用官方推荐的v0.5；官方README说明它修复v0.1问题。
源代码固定Git提交 `f3a237e434ae987bc38281476d6cfb5df3e4d739`，本机所用38个源文件逐一校验Git blob。
从官方链接的ModelScope模型仓库取得 `model.pt`，1,284,837,952字节，
SHA-256 `b60cf27ddbd0e51e9b59b03475c0d39d02d2e48ecf8dbb5866f04d46802b3c23`；
固定仓库修订 `8d8942390f40f5c4e2e0c3b3e0964d94d9fe5afc`。
此处保证本机下载与发布仓库哈希匹配，未宣称不同托管站点权重逐字节比对。
Hugging Face访问超时、镜像403，改用项目明确给出的ModelScope来源；没有换成其它模型。

输入单位米，无效深度置0；内参第一行除宽、第二行除高；输出恢复到原图分辨率。
已验证本机torch2.7导入，未按上游安装文件重装torch2.6/xformers，从而保留既有运行环境。
首次实际推理发现嵌套张量路径必须使用xFormers；已在`.deps/lingbot`隔离安装
PyTorch官方CUDA12.8索引的xformers0.0.30，使用`--no-deps`保留原torch2.7；
没有改写LingBot网络或替换权重。首次依赖失败记录保留，成功推理另列。
初始实时条件固定 `resolution_level=0`（上游允许的最低token档）；默认9作为单独质量/时间消融，
不得把最低档的延迟当默认最高档性能。

[代码校验回执](../../results/lingbot-depth-source.json)；
[权重校验回执](../../results/lingbot-depth-download.json)。

### 首轮本机测量（不等同任务收益）

同一公开录制的铲子初始帧，SAM目标mask为2628像素，干净渲染深度作离线参考。
LingBot最低0档在干净输入上的目标RMSE为2.34cm，默认9档为1.89cm；
参考深度本身没有误差，故本帧精修改变了正确几何。给输入加入10mm高斯噪声后，
目标输入RMSE为1.04cm、0档输出为2.45cm，没有改善该噪声条件。
30%随机空洞条件下，目标覆盖率从69.9%补到100%；柄部块状空洞条件从79.0%补到100%。
补齐不代表精确：缺失区与原有效区分别报告误差，不能凭输出全覆盖就宣称抓取更可靠。

本帧0档首次前向0.264秒、热前向0.069–0.074秒；9档单次前向0.227秒，
冷/热顺序不同，不构成稳定吞吐基准。在线H3与模拟器/π0.5共用3090，
0档热前向0.079–0.085秒，首次0.257秒，SAM+LingBot模型加载另计。
只测了一个开发帧和人工退化，尚未验证真实传感器或默认9档的退化改善。

因此将LingBot优先放在真实空洞、严重噪声条件测试；保留原始深度作显式对照，
下一步增加“仅填无效点、保留有效点”与“全图精修”的消融。
该机制可以减少改坏原有效深度的风险，但填补位置仍需检验，当前尚未实现线上此组。

[完整深度消融数据](../../results/lingbot-depth-audit-20261013/results.json)；
[Astra闭环任务对照](../../results/astra-hybrid-perception/report.zh-CN.md)。

## 要验证的效果，先不预设结论

- 深度是否减少 Astra 的试探移动与视觉距离判断错误，并让接近/下降更准？
- 分割是否减少错物体、错部位，并让 Astra 正确拒绝偏离目标的π0.5提议？
- LingBot 是否只在空洞/噪声条件有收益，还是改变了原本正确的细柄深度导致失败？
- 感知调用的额外时间是否小于节省的Astra等待与纠错时间？
- 感知错误是否被 Astra 识别，还是诱导更自信的错误动作？
- 相同物体不同布局及未见物体是否保持收益，而不是仅改善已开发铲子案例？

必须同时报告任务成功、正确抓放次数、420秒预算完成、动作/纠错次数、
Astra请求/等待/用量、感知加载/热推理/端到端时间，以及观测年龄。
感知的离线精度只能解释结果，不能代替Astra实际执行任务的主评测。

原始资料保存在[来源目录](../../results/perception-method-survey-20261013/sources.json)。
其中首次试探URL的404也保留；UniDepth已纠正为上述官方地址，未找到的Any3D不列入推荐。
