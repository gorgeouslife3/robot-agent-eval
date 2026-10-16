# Robot Agent Eval

用于 **RoboDojo 机器人仿真评测与协作开发**的实验框架。包含 Direct、π₀.₅、Hybrid、ReAct + task skill，以及 RPent、GaP、PhyAgentOS 的适配代码、资源记账与配对比较工具。

A research workspace for paired robot-agent evaluation in RoboDojo, with explicit native outcomes, resource budgets, and auditable attempts.

这是从本机实验工作目录整理的轻量发布版：包含代码、测试、配置模板、冻结清单、实验设计和精选历史报告。仿真器、模型权重、第三方源码、原始运行目录及录像需要另行准备。历史记录保留失败和未知结果；当前数据是小样本接入与机制实验，不能当作完整 benchmark 排名。

## 先运行离线测试

Linux、Python 3.11 或 3.12。以下步骤不启动 GPU 仿真、不调用付费模型：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
# 从 source-lock.json 恢复测试所需的外部源码及官方 skill，校验版本与归档哈希。
python scripts/bootstrap_sources.py
python -m unittest discover -s tests -v
python -m unittest discover -s experiments/supervision-efficiency/implementation -p 'test_*.py' -v
python -m robot_agent_eval.cli methods
```

GitHub Actions 对 Python 3.11 / 3.12 执行相同离线测试。它验证接口和记账约定；真实仿真成功需要原生评测结果。

## 在自己的机器做仿真

1. 单独安装 [RoboDojo](https://github.com/RoboDojo-Benchmark/RoboDojo) 及其 NVIDIA/Isaac、机器人资源和子模块，按上游说明验证仿真器可启动。
2. 配置解释器与源码路径，在仓库根目录运行：

   ```bash
   export ROBODOJO_ROOT=/absolute/path/to/RoboDojo
   export ROBOT_EVAL_SIM_PYTHON=/absolute/path/to/robodojo-env/bin/python
   export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
   ```

3. 在你的仿真解释器安装本项目。依赖环境不同，可保留专用环境；先运行 inventory，生成属于当前机器的路径和原生源码哈希：

   ```bash
   "$ROBOT_EVAL_SIM_PYTHON" -m pip install -e .
   "$ROBOT_EVAL_SIM_PYTHON" -m robot_agent_eval.cli inventory
   # 仅检查仿真和原生终止链路，不调用模型。
   "$ROBOT_EVAL_SIM_PYTHON" -m robot_agent_eval.runner --method hold_calibration --config configs/model.example.json
   ```

4. 从模板建立忽略提交的本机模型配置，填写实际模型名称、Responses 服务地址和预算：

   ```bash
   cp configs/model.react-pilot.json configs/model.local.json
   # 编辑 configs/model.local.json 的 model / base_url / reasoning_effort。
   export OPENAI_API_KEY='your-provider-key'
   "$ROBOT_EVAL_SIM_PYTHON" -m robot_agent_eval.runner      --method astra_react_skill --manifest manifests/pilot.json      --task general_pickup --layout 1 --limit 1 --config configs/model.local.json
   ```

   也可使用 `secrets/api-key.json`（形如 `{"OPENAI_API_KEY":"..."}`）；凭据文件仅保存在本机。环境变量优先，模板中不包含真实服务地址或密钥。配置预算是历史实验的起点，请按自己的资源调整。

π₀.₅ / Hybrid 另外需要 OpenPI/JAX 专用环境和策略权重，代码默认查找 `.venvs/openpi-existing/bin/python`。权重下载清单在 `checkpoint-download-manifest.json`；`python -m robot_agent_eval.download_checkpoint` 可按文件大小与 SHA-256 校验下载。框架方法另需各自的依赖、感知模型和模型服务；可用 `python scripts/bootstrap_sources.py --names rpent gap_skills` 补取锁定源码。更多要求见 [仿真复现说明](docs/REPRODUCIBILITY.zh-CN.md) 和 [框架试跑说明](FRAMEWORK-PILOT.md)。

## 目录与优先阅读

| 路径 | 用途 |
| --- | --- |
| `robot_agent_eval/` | 单案例执行、原生仿真桥、控制器、资源预算、结果汇总 |
| `harness/` | ReAct 公共接口、任务 skill 与按指令路由 |
| `tests/` | 动作边界、反馈循环、记账、感知与框架接口回归测试 |
| `configs/` | 无密钥配置模板；`model.local.json` 留在本机 |
| `manifests/` | 布局 ID、split、哈希；使用前按本机环境重新生成 |
| `experiments/` | 感知/执行器/监督策略实验设计与隔离实现 |
| `designs/` | 后续闭环 skill 设计与评审 |
| `results/` | 精选历史摘要与比较报告；完整轨迹未随 Git 发布 |
| `source-lock.json` | 外部源码版本、来源与下载身份 |

先读 [实验总报告](report.zh-CN.md)、[任务目录](robodojo-task-catalog.zh-CN.md)、[ReAct harness](harness/README.zh-CN.md)、[监督策略实验设计](experiments/supervision-efficiency/plan.zh-CN.md)。[原工作目录说明](README.zh-CN.md) 作为历史记录保留，其中的运行目录及部分链接需要本机原始数据。

## 共同修改与提交结果

通过 Issue 讨论问题，fork / 分支开发后提交 PR。可从安装可移植性、更多任务 skill、适配器契约和失败分析入手；细节见 [CONTRIBUTING.md](CONTRIBUTING.md)。

一次运行建立一个新 `runs/<id>/`，原生成功、预算内成功、服务/部署故障分别记录。正式比较使用相同布局、相同预算及冻结实现，保留全部尝试，不选最好一次。模型自报完成或退出码 0 不能替代原生成功；预算截断时原生结果保持未知。

提交实验时附代码 commit、环境、manifest/配置/skill 哈希、所有尝试摘要及配对条件。录像、权重和完整日志使用单独的附件或数据存储。不要直接覆盖仓库里的历史汇总；建议新建 `results/<experiment-id>/`。

本仓库原创部分使用 MIT；上游源码、模型和资源遵循各自许可证，见 [THIRD_PARTY.md](THIRD_PARTY.md)。
