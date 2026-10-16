# Astra 操作后端配对对比

更新时间：2026-10-14T10:01:22.380553+08:00。状态：stopped。

已结束 40 / 690 次；当前：无。

按文档的全部 10 配置运行。先 30 个开发案例 × 3 条件，再 100 个测试案例 × 3 条件 × 2 遍，共 690 次。
开发和测试分开；已有铲子开发结果不并入。AnyGrasp 按用户要求暂缓。

共同条件：gpt-6-astra/xhigh、三相机 RGB、相同头部原始深度/标定、1200 秒控制墙钟、60 请求、200 万 token、60 决策；每任务原生步数上限保持原值。
VLA 使用原 π0.5 和失败/意图接管门；GraspNet-only 无 VLA，Astra 可直接规划 bounded EEF；组合组保留原门并增加真实候选。
这是完整架构比较：VLA 可以每决策执行 15 步，EEF 为 5 步，观测/模型成本及门控不同，不能归因成单个网络的纯质量差。
GraspNet 指已固定第三方 PyTorch Contact-GraspNet，不代表所有 GraspNet 实现。抓取候选不提供推、插、放或双臂协调轨迹；这些阶段由 Astra 规划。
SAM 使用实时 Astra 的文本或当前帧像素提示，统一阈值 .2；分割失败和候选空集均保留，不降低阈值、不回放语义种子。

| 分组 | 配置 | 条件 | 已结束 | 预算内成功 | 原生成功/失败/未知 | 基础设施错误 | 控制均时秒 | 请求均数 |
|---|---|---|---:|---:|---|---:|---:|---:|
| development | general_pickup | vla | 3 | 2 | 2/0/1 | 0 | 916.7 | 22.0 |
| development | general_pickup | graspnet | 3 | 0 | 0/0/3 | 0 | 1206.3 | 27.7 |
| development | general_pickup | vla_graspnet | 3 | 2 | 2/0/1 | 0 | 1029.7 | 25.3 |
| development | push_T | vla | 3 | 0 | 0/0/3 | 0 | 893.5 | 21.3 |
| development | push_T | graspnet | 3 | 0 | 0/0/3 | 0 | 1163.0 | 28.7 |
| development | push_T | vla_graspnet | 3 | 0 | 0/0/3 | 0 | 996.0 | 23.0 |
| development | stack_blocks | vla | 3 | 0 | 0/0/3 | 0 | 988.9 | 25.7 |
| development | stack_blocks | graspnet | 3 | 0 | 0/0/3 | 0 | 1049.7 | 27.3 |
| development | stack_blocks | vla_graspnet | 3 | 0 | 0/0/3 | 0 | 970.8 | 26.3 |
| development | insert_tubes | vla | 3 | 0 | 0/0/3 | 0 | 1000.7 | 26.0 |
| development | insert_tubes | graspnet | 3 | 0 | 0/0/3 | 0 | 1070.6 | 28.7 |
| development | insert_tubes | vla_graspnet | 3 | 0 | 0/0/3 | 0 | 927.7 | 25.7 |
| development | swap_blocks | vla | 1 | 0 | 0/0/1 | 1 | 3.7 | 1.0 |
| development | swap_blocks | graspnet | 1 | 0 | 0/0/1 | 0 | 1025.5 | 29.0 |
| development | swap_blocks | vla_graspnet | 2 | 0 | 0/0/2 | 1 | 17.3 | 1.5 |

原生未知保持未知；预算停止单列为预算内未成功。基础设施错误不当作任务能力失败；检查逐次日志后判断可比性。配对差值仅使用两组均具有效任务记录的相同测试案例/遍次，按案例合并重复后 bootstrap；小样本区间仅供参考。
服务失败请求也消耗共同预算；各次失败请求数另记，服务异常期间的预算结果体现运行可靠性，不能解释成后端任务能力。

候选生成、候选空集、分割失败、EEF/VLA 步数与逐次公开决策理由保存在 summary.json / records.jsonl 和 run 原始文件；公开理由属于模型自述，不证明因果。

## 优劣的评估边界

- VLA：检验其在推、长流程、双臂配合中的轨迹与模型调用效率，同时检查抓偏、错误阶段及接管需求。
- GraspNet-only：检验当前点云候选能否帮助抓取定位及姿态；同时量化后续运动、放置、插入、回臂需要 Astra 规划的成本。
- 组合：检验候选能否改善 VLA 的抓取失败，并测量加载、分割、推理和门控带来的额外成本。

以上是预注册评估问题；只有实际配对数据足够后才给任务适用性结论。全任务等权平均只在任务覆盖完整时报告。

停止原因：Three consecutive infrastructure/zero-step controller failures; inspect logs before resuming
