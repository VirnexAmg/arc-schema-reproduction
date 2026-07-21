# 第一阶段进展

日期：2026-07-21

## 已实现

- 统一 `Environment` 协议和 `ArcEnvironmentAdapter`；
- baseline 单动作决策；
- 声明式有限状态 world model（不执行模型生成代码）；
- 对完整运行历史逐条 backtest，并报告首个 mismatch；
- backtest/current-state 校验失败时不允许规划或调用 `env.step()`；
- 有最大节点数的 BFS；
- 计划逐步提交，真实 observation 与预测不一致时立刻丢弃剩余计划；
- observation、transition、模型原始响应及失败的 SHA-256 哈希链 JSONL；
- 模型逻辑调用、含重试 API 尝试、token、可选成本、真实动作及 wall-clock 指标；
- baseline/harness 共用游戏、seed、动作预算、模型配置和重试策略；
- 逐次结果与均值、样本标准差、完成率的机器可读汇总。

## 实际验证

- 锁定版本：`arc-agi 0.9.9`、`arcengine 0.9.3`；
- `uv run pytest -q`：6 tests passed；
- `uv run ruff check .`：All checks passed；
- `uv run arc-schema arc-smoke --max-actions 1`：
  本地离线创建 `ls20-9607627b`，动作空间为 1–4，执行 ACTION1 后
  `state=NOT_FINISHED`、`levels_completed=0`，成功读取帧与 scorecard。

## 使用 mock 验证

- 正确 world model 通过两条历史 transition；
- 错误模型在第 0 条 transition 返回预测/现实差异；
- BFS 在玩具世界找到两步最短路径；
- current state/backtest 门禁失败时真实动作数为 0；
- 首步预测不符时，原计划第二步未执行，并发生新的模型构建调用；
- baseline/harness A/B 均可从零运行至 WIN，并保存完整 JSON/JSONL。

## 尚未验证

- 未调用真实 DeepSeek API，因而尚未验证目标 model ID、供应商是否接受
  `seed`/`response_format`、真实 token 统计和响应质量；
- 未进行多次真实 `ls20` A/B，不能得出涨分结论；
- 声明式有限状态模型对复杂 ARC 游戏的表达能力和上下文成本未知；
- 未验证 ACTION6 的坐标动作游戏；
- 未配置外部不可变日志存储或 CI。

## SDK 实际行为与常见 Gym 假设的差异

- `env.step()` / `reset()` 返回 `FrameDataRaw | None`，不是 Gymnasium 五元组；
- 终止由 `state in {WIN, GAME_OVER}` 判定，没有独立 reward/done；
- `FrameDataRaw.model_dump()` 不包含像素，像素位于运行时 `frame` 属性；
- 环境创建时自动 reset；合法动作应每步读取 `available_actions`；
- `make/step/reset` 的部分失败路径返回 `None` 而非向调用方抛异常；
- scorecard 的 `completed` 等价于整局 `state == WIN`，过一关只增加
  `levels_completed`。

## 已知限制与后续

当前模型使用对最后一帧的逐行 RLE 快照做严格相等比较。它简单、可执行且安全，
但让模型预测完整未来帧可能昂贵。获得真实 smoke 数据后，再评估是否引入同样可
执行、但更紧凑的对象级 schema；不能为了提高通过率而改成可被空字段绕过的宽松
比较。

## DeepSeek V4 Pro 初步真实实验

2026-07-21 使用端点实际列出的 `deepseek-v4-pro` 在本地离线 `ls20` 上进行了
受控 pilot。没有扩大到完整题集。

- 默认 thinking + 2048 输出预算：baseline/harness 均因推理耗尽预算而返回空
  content；环境动作均为 0。此结果不计入能力对比。
- non-thinking 单步闭环：baseline 执行 ACTION1；harness 生成计划并执行
  ACTION1，随后正确发现预测帧与现实不一致并停止剩余计划。
- 单步 token：baseline 1507，harness 3394；耗时分别约 2.33 秒和 14.14 秒。
- 5 动作 pilot：baseline 连续选择 5 次 ACTION1，完成 0/7 level；harness
  生成重复状态快照，安全门禁拒绝 world model，完成 0/7 level且未执行动作。
- 当前表面完成率均为 0%，但样本数仅 1，且 harness 为协议/模型校验失败，不能
  解释为“二者能力相等”或“harness 没有提升”。

实验暴露并修复了三项工程问题：V4 thinking 显式配置及失败 token 记录、已知
observation 的不可改写 `snapshot_ref`、Windows 原子结果写入重试。baseline
也改用相同 observation 引用，避免历史中重复发送完整帧造成不公平 token 膨胀。

真实日志位于 `pilot-runs/`（本地忽略，不提交）。在对象级 world model 或更可靠
的冷启动探索协议完成前，不应进行大规模 API 评测。

## Thinking-high 30 动作正式配置尝试

另一次并行启动的 8,192-token 配置（实验 ID
`20260721T123523.241658Z`）也已结束：baseline/harness 均只执行 1 个动作，
第二轮请求因空 content/JSON 解析失败终止。Baseline 总计 25,965 token，
Harness 31,013 token并记录 1 次预测 mismatch；两组仍为 0/7 level。该结果进一步
说明 8K thinking 预算不足以稳定完成连续视觉决策。

2026-07-21 使用 `max_actions=30`、`runs=1`、`retries=1`、
`thinking=enabled/high`、`max_tokens=16384`、历史窗口 30 和 timeout 120 秒
运行了一次有实际过关可能的配对实验。实验 ID：
`20260721T123659.868822Z`。

- Baseline：执行 3 个动作（ACTION1、ACTION2、ACTION2）后，第 4 次模型决策失败；
  其中一次响应耗满 16,384 reasoning token，后续重试超时。
- Baseline 累计 18,185 prompt、51,685 completion，其中 51,643 reasoning，
  cache hit 7,424，总计 69,870 token；按官方价格估算 $0.04967。
- Harness：首次 world-model 请求两次均发生 `APIConnectionError`，没有返回 usage，
  没有执行真实动作。
- Baseline wall-clock 约 18.4 分钟；Harness 约 53.1 分钟；完整实验约 71.8 分钟。
- 两组均完成 0/7 level、score 0，但均未完成动作预算，因此不能用于能力或正确率
  对比，只能判定该 thinking-high 配置在当前 API 稳定性与延迟下不可操作。

原始结果保存在本地
`experiment-runs/20260721T123659.868822Z/experiment.json` 及对应哈希链 JSONL。
下一次正式 A/B 应先选择可操作的推理策略（例如 non-thinking 或受控 reasoning
预算），并增加整局超时和单 Agent 失败后的配对失效标记。

## DeepSeek V4 Pro 表现提升改造（2026-07-21）

已实现计划中的工程改动：

- 稀疏 `FrameDelta` / `snapshot_patch` 物化，最终仍严格比较完整 snapshot；
- 共享紧凑上下文（当前全帧 RLE + 历史 delta + untried actions）；
- `vision-smoke`：官方端点拒绝 `image_url` content-part，回退 RLE+delta；
- Explore-then-Compact-Plan：前 6 步确定性探索，之后最多 3 步计划，失败回探索；
- 单局 600s 硬超时、模型调用上限、API 失败降级动作、`paired_valid` 过滤。

### 验证

- `pytest`：16 passed；`ruff`：通过；`arc-smoke`：通过。
- Vision probe：不接受 PNG content-part → `rle_delta_fallback`。
- Phase 0（`pilot-runs/20260721T153304.204086Z`）：双方均执行 8 步、无 `failed`、
  `paired_valid=true`；baseline ≈$0.0047，harness ≈$0.026。
- Phase 1（`experiment-runs/20260721T153600.641677Z`，50 动作，non-thinking）：
  - Baseline：50 动作耗尽，0/7 level，≈$0.059，92.5s。
  - Harness：17 动作后 `timeout`，0/7 level，18 次 backtest 失败，0 次计划执行，
    ≈$0.135，646.8s。
  - 目标 `levels_completed >= 1`：**未达成**。
  - 因 harness `timeout`，pair 记为 `paired_invalid_reason=harness_timeout`，
    **不计入能力差值样本**（基础设施/超时，不是 0% 能力结论）。
