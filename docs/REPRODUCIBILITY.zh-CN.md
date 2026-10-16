# 仿真与复现边界

离线测试只依赖 CPU Python 包及锁定的 Astra / GaP / PhyAgentOS 源码；以及 `runtime-source-lock.json` 锁定的官方 RoboDojo skill；源码按需从上游下载，不随本仓库重新分发。`scripts/bootstrap_sources.py` 使用 `source-lock.json` 中的 commit 和已记录的归档 SHA-256。官方 skill 从匿名 registry 获取临时下载地址，归档大小与 SHA-256 必须匹配锁文件；上游更换制品时拒绝继续。失败时返回非零退出码，不退回最新版本。

真实仿真还依赖 RoboDojo、Isaac、机器人资源、GPU 驱动，以及所选方法的 VLA、感知或模型服务。原工作目录的 Python 环境和权重没有被打包。基础包不强行安装 GPU 依赖，以免混用 PyTorch/JAX/Isaac 环境。

## 原生身份和布局

历史 `manifests/inventory.json` 记录 RoboDojo、XPolicyLab、IsaacLab、cuRobo 的 Git 身份、dirty 状态和关键文件哈希。它们是历史环境证据，不保证上游当前版本与之相同。发布版将工作站路径替换为占位符，因此要先用本机仿真解释器运行 `python -m robot_agent_eval.cli inventory`。这会重建 `manifests/`；保存新的 commit 或将其单独归档，避免把新环境混入历史结果。

`ROBODOJO_ROOT` 指定仿真器根目录，默认查找本仓库旁边的 `RoboDojo`。`ROBOT_EVAL_SIM_PYTHON` 指定仿真解释器，默认当前 Python。`ROBOT_EVAL_ASTRA_ROOT` 可选，用于指定已有的锁定 Astra 源码。路径在进程启动时读取。

同布局/seed 不代表物理状态逐位一致。运行时仍记录初始图像与机器人状态指纹。测试布局由评测器读取，控制 agent 不能访问布局内容或隐藏物体真值。

## 配置和依赖

`configs/` 里的服务地址均为占位符。使用 `configs/model.local.json` 保存本机设置；不要直接运行占位配置。环境变量 `OPENAI_API_KEY` 优先于 `api_key_file`；相对凭据路径以仓库根目录为基准。

Direct / Hybrid 的原生工具循环依赖上游编码代理运行时；执行前检查 `robot_agent_eval.controller_preflight` 的输出并按上游要求安装。ReAct 通过 Responses 直接请求，支持范围仍以 skill 注册表和实际任务指令为准。不要把不支持的任务直接记为机器人失败。

π₀.₅ 默认解释器是 `.venvs/openpi-existing/bin/python`，默认权重位于 `checkpoints/ckpt/RoboDojo/Pi_05/RoboDojo-sim-arx_x5-joint-0/59999`。OpenPI、SAM、GraspNet、LingBot 等须各自准备兼容依赖和权重；历史安装版本可参考 `configs/openpi-inference-requirements.txt`，但它不是跨机器通用锁文件。感知方法需与配置中指定的虚拟环境路径一致。

## 历史结果和新增批次

精选报告保留原运行 ID、数值和未知值，工作站地址已清理；原始视频、逐轮文字和大体积传感器文件未发布。因此报告里指向 `runs/`、完整输入文本或未选入诊断文件的链接不一定可用，精选报告本身不足以独立复核全部历史结论。新结果请随独立数据附件提供这些证据。

`experiments/supervision-efficiency/` 中以 `.historical.json` 结尾的冻结记录保留原实验哈希。发布整理改变了路径和少量实现，原冻结签名不能代表发布代码。不要重用旧冻结直接启动历史队列；应在独立批次更新配置，并按照历史冻结记录的结构重新生成配置、实现和依赖的校验值后再启动队列；当前没有通用的冻结生成命令。这个实验目前仍是单场景试跑，不能推断为全部任务效果。

CI 和本机离线测试不产生真实仿真评测；接入成功、下载完成和单案例成功也不等于全量 benchmark 完成。
