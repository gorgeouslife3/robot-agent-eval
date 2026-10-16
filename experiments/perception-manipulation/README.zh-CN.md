# 首批感知/操作消融入口

## 当前条件

- `configs/ablations/astra_rgb-v2.json`：Astra RGB估计XYZ、RGB像素轴方向。
- `configs/ablations/astra_depth-v2.json`：同目标选择契约，深度反投影XYZ/轴。
- `configs/ablations/sam_depth-v2.json`：初始Astra语义种子，后续SAM+深度；局部点云主轴。
- `configs/ablations/sam_depth-recovery-v2.json`：上一条件开启一次本地恢复。
- `sam_depth-replay*.json`：复用已记录语义种子的单场景接口诊断，不并入实时主对照。
- `sam_depth-replay-shallow*.json`：首次高于目标35mm闭合，成对测试本地恢复；可控故障单列。
- `sam_depth-graspnet.json`：真实Contact-GraspNet候选生成/筛选+共享DLS执行；`-replay`版本复用语义种子。

所有v2组使用相同SAM点锚+深度验证、相同本地几何/DLS执行器与420秒控制进程预算。
模型请求沿用固定Astra/xhigh与计数代理；常驻SAM推理和加载分开记录。
模型思考/感知更新的调用次数是变量引起的结果，不强行配平调用数。
几何动作不是GraspNet动作；后者保存真实候选与被选索引。每个runner调用新建目录，不重置试验内场景、不覆盖失败。

## 单案例运行（严格串行，共享一张3090）

```bash
cd /path/to/robot-agent-eval
/path/to/robodojo-env/bin/python -m robot_agent_eval.runner \
  --method modular_calibration --manifest manifests/pilot.json \
  --task general_pickup --layout 1 --config configs/ablations/sam_depth-v2.json

/path/to/robodojo-env/bin/python -m robot_agent_eval.runner \
  --method modular_pickup --manifest manifests/pilot.json \
  --task general_pickup --layout 1 --config configs/ablations/sam_depth-v2.json

# 修改config路径即可运行其余主对照；本例layout1仅作开发回归。
# 未见布局批次应另外冻结manifest并记录重复次数、各组顺序。
```

## 真实Contact-GraspNet候选生成

```bash
.venvs/frameworks/bin/python -m robot_agent_eval.graspnet_probe \
  --frame runs/20261011-212848-178623-rpent_astra-general_pickup-l1/controller/sensors/initial \
  --mask results/perception-ablation-pilot-20261013-v3/frame-000/sam-current-seed.png \
  --output results/contact-graspnet-next-probe
```

来源/权重来自固定Git树验证，兼容补丁来自ASPIRE。依赖隔离在`.deps/graspnet`，
未替换原有torch/numpy。候选是Panda-base抓取姿态，需另行验证ARX接触中心和开口转换，
此命令不运行机器人，也不产生抓取成功分数。

只读可达性检查使用`runner --method graspnet_calibration`，其余参数同上；
候选转换使用原库平面指垫中心0.1034m，原生IK分别检查双臂的预抓取和抓取姿态。
执行条件用`--method modular_pickup --config configs/ablations/sam_depth-graspnet.json`。
SAM3的tracking predictor会保留CUDA BF16 autocast上下文；GraspNet邻域距离计算
必须显式禁用autocast和TF32，模型加载/前向使用FP32，退出时还原调用方TF32状态。
每次推理在`controller/graspnet/numeric_runtime.json`记录继承状态与实际设置。
单独关闭TF32不足以修复本轮发现的CUDA索引故障。
首次GraspNet执行限制SAM-depth输入，选择接近语义抓取点的顶部候选，不默默回退几何抓取。

## 检查与报告

```bash
PYTHONPATH=source-snapshots/phyagentos .venvs/frameworks/bin/python -m unittest discover -s tests -v
.venvs/frameworks/bin/python -m robot_agent_eval.compare_ablations
```

完整逐次结果在`results/perception-manipulation-ablation/attempts.json`；
每次运行的`framework_trace.jsonl`保留感知来源、消费的世界目标、TCP目标和实测误差，
`sim/evaluation_outcome.json`才是独立原生判分。

首次重置超时、旧RGB-only记录缺标定、SAM导入修复、模型429、验证低置信和
GraspNet下载故障都保留原记录。录制帧一致性不当作定位准确率；
初始帧重置重复与录制种子回放不当作未见场景。
