# Astra hybrid：VLA 与 Contact-GraspNet

2026-10-13 启动。用户确认暂不接 AnyGrasp（本机没有 SDK、权重和许可证）。
复用本目录 README 的全部 10 个配置，开发清单 30 例，测试 screening 清单 100 例。

| 条件 | 提议 | Astra 职责 | 运动执行 |
|---|---|---|---|
| `vla` | 原 RoboDojo π0.5 50×14 关节轨迹 | 原失败/意图 gate，审查及接管 | student 每次最多 15 步；edit/eef 最多 5 步 |
| `graspnet` | 当前 RGB-D、实时 Astra 文本/像素、SAM3、真实 Contact-GraspNet 候选 | 抓取与所有非抓取阶段规划；无 VLA、无虚构接管门 | 原 bounded EEF/DLS，每次最多 5 步 |
| `vla_graspnet` | 上述两种提议同时可用 | 原 gate，判断候选是否适合纠正 VLA | 同 `vla` |

共同三相机 RGB/proprio、头部原始深度网格/标定；无布局真值、物体状态或回放语义种子。
抓取提示在 `pi05_infer` 服务参数 `target_text` / `grasp_pixel_rc` 由当前 Astra 选择；服务名称为旧协议名称，GraspNet-only 不运行 π0.5。
像素是原头部图像的 `[row,col]`，可用 null 选择纯文本分割；空文本代表当前不需要新抓取。
SAM 阈值统一 .2；空 mask/空候选和报错均返回并记录，不降低阈值或替换几何抓取。
候选坐标转换复用已校准的 Panda 夹持中心 .1034 m / ARX link6→TCP .145 m；9 cm pregrasp。
给出两种对称夹爪方向、预测开口及名义 6.5 cm 开口兼容提示，不声称可达、无碰撞或已抓住。

预算采用 `model.pilot.json`：1200 秒控制墙钟、60 次模型请求、200 万总 token（含缓存输入）、60 控制决策、gpt-6-astra/xhigh、不回退模型、图像预览最长边 480。
原生任务上限保持不变。启动/加载、控制、模型等待、候选推理、原生步骤分别记录。
这是系统架构对比；不同动作块长、门控和 Astra 规划责任不能伪称为只替换网络的消融。
同一预算下 GraspNet-only 可执行步数较少也是需要量化的实际成本。

先完整开发轮（30×3=90 次），再测试（100×3×2=600 次）。案例内轮换条件顺序；两遍测试顺序改变。
只在开发轮修接口；测试开始后禁止调提示词/skill。运行前冻结适配源码、配置、清单哈希。
旧铲子开发结果与 10/13 的录制帧/服务校准均不并入主表。所有重复、错误、未知原生分数保留。
报告分任务、标准/随机、开发/测试，统计预算内成功、原生成功/失败/未知、服务故障、候选空集、耗时/请求及决策记录。
完整配对测试后比较差值，按案例合并重复进行 bootstrap；覆盖不足不给总体能力结论。

入口（单 GPU 串行，可恢复；会生成状态和动态报告）：

```bash
/path/to/robodojo-env/bin/python -m robot_agent_eval.classic_hybrid_campaign \
  --output /path/to/robot-agent-eval/results/classic-hybrid-backends-20261013
```

报告：`results/classic-hybrid-backends-20261013/report.zh-CN.md`。
逐次主索引：`records.jsonl`；冻结计划：`plan.json`；队列与进度：`state.json`。
每次完整配置、原始动作与视频位于索引中的 `run` 路径。
在输出目录创建 `STOP` 会在下一例开始前停止；当前已授权的有界案例正常结束。
连续三例基础设施/零动作初始化错误，或连续三例各有至少三次模型服务失败且没有原生结束时，队列停止，防止在不可用服务上消耗整个测试集。
剩余磁盘低于 20 GiB 时停止下一例。源码/配置/清单改变也停止，不将版本不同的结果混入冻结实验。

截至接入校准：54 项离线测试通过。新的修正带录制帧上，文本 SAM（白色修正带）低于 .2 阈值；点 SAM score=.8203、205 个点，真实 Contact-GraspNet 单次前向（约 .86 秒）返回 0 候选。
这是该帧感知/候选诊断，尚不是端到端任务成功率或 GraspNet 总体能力结论。
