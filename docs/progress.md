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

## Phase 1 harness 诊断与修复（2026-07-22）

### 诊断摘要

对 `harness-run-0.jsonl` 抽样后，18 次 backtest 失败 / 0 planned_actions 的主因是：

1. **工程不一致**：prompt/catalog 只用 `history[-12:]`，但 `backtest` 扫全历史；
   窗口外 early transitions 导致即便模型完美覆盖窗口也会 `before observation absent`。
2. **模型常交迷你 WM**（2 states），忽略已知历史。
3. **PASS 两次均无 goal** → BFS `no_plan`。
4. **失败后立刻重建 WM** + JSON 截断重试，把 600s 超时吃光。

### 已落地修复（A+B+C+D）

- **A**：`backtest(..., limit=context_transitions)` 与 compact context 对齐。
- **B**：`build_history_skeleton` 程序注入已知历史 FSM；模型只返回 extension，
  经 `merge_world_model_extension` 合并后再物化/校验。
- **C**：无 goal / 无当前出边 / 无法在 `max_plan_steps` 内达 goal → 明确 feedback 重试。
- **D**：`explore_burst=3`（失败后连续探索再重建 WM）；
  `wm_time_reserve_seconds=120`（剩余时间不足则只探索不调 WM）。

### 验证

- `pytest`：20 passed；`ruff`：通过；`mock-ab`：通过。
- **尚未**再次花费真实 API；需用户确认后再跑 Phase 0（8 actions）/ 第二次 50-action。

## 真实 API 续跑（2026-07-22）

预算上限约 ¥20（按 $1≈¥7.2）。本日累计约 **$0.82 / ¥5.9**，剩余约 ¥14。

### 工程修复（跑实验中追加）

- `.env` CRLF 导致 API key 尾部 `\r` → `APIConnectionError`；已 strip，且
  `load_dotenv(override=False)` 避免盖住 shell 实验参数。
- **禁止假 goal**：`goal` 必须 `levels_completed > known` 或 `state=WIN`
  （否则模型把中间帧标成 goal，计划“匹配”但永不加关）。

### 实验结果（均为 offline ls20，deepseek-v4-pro，non-thinking）

| 实验 ID | 配置 | Baseline | Harness | paired_valid | 费用 |
|---------|------|----------|---------|--------------|------|
| `pilot-runs/20260722T020706...` | 8 act | 8/0lv | 7ex+1pl / 0lv / mm=1 | yes | $0.004 |
| `experiment-runs/20260722T020735...` | 50 act（假 goal 未禁） | 50/0lv | **34 planned** / 0lv / mm=3 / bt=2 | yes | $0.144 |
| `pilot-runs/20260722T021551...` | 8 act + 真 goal | 8/0lv | 7ex+1pl / mm=1 | yes | $0.004 |
| `experiment-runs/20260722T021617...` | 50 act + 真 goal | 50/0lv | 11pl / **0 match** / mm=11 | yes | $0.086 |
| `experiment-runs/20260722T022150...` | 80 act（plan 仍=3） | 80/0lv | 19pl / mm=18 | yes | $0.139 |
| `experiment-runs/20260722T023021...` | 80 act, explore=12, plan=8 | 80/0lv | 13pl / mm=13 | yes | $0.125 |
| `experiment-runs/20260722T023642...` | **3 seeds**×50, explore=8, plan=5 | 全 0lv | 全 0lv；3/3 valid | yes | $0.189 |

对比旧 Phase 1（timeout@17, planned=0, bt_fail=18）：
基础设施已恢复可评测——双方常跑满动作预算，`paired_valid=true`，harness 能生成并提交计划。

### 能力结论（当前）

- 目标 `levels_completed >= 1`：**仍未达成**（baseline/harness 均为 0）。
- 多 seed 能力差：`harness_minus_baseline.levels_completed.mean = 0`（3 个有效 pair）。
- 真 goal 约束后：计划几乎全部 `prediction_mismatch`——模型会假设“一步过关”，
  但预测帧与现实不符；不再出现假 goal 空转匹配。

### 剩余瓶颈（非超时）

1. 模型难以用 sparse patch 猜中真实过关帧；
2. 短视野计划（即使 8 步）对 ls20 第一关可能仍不够；
3. 仅靠 ACTION1/2 探索循环，未形成有效过关策略。

后续若继续花钱，应换假设（例如中间路标 goal、更强的转移摘要、或更长探索课表），
而不是重复同一 50-action 配置。

## Schema 对齐 Harness v2（2026-07-22）

对照 [Schema 官方说明](https://schema-harness.github.io/) 将默认 harness 升级为程序世界模型环：

- 受限沙箱执行模型生成的 `step(state, action)` / `is_goal(state)`
  （[`sandbox.py`](../src/arc_schema/sandbox.py)、[`program_world_model.py`](../src/arc_schema/program_world_model.py)）
- Deliberation 工具：`write_code` / `run_backtest`（全 Timeline）/ `run_bfs` /
  `commit_actions`（唯一环境通道）/ notes（[`deliberation.py`](../src/arc_schema/deliberation.py)）
- 持久 Workspace：`world_model.py` + `notes.md`
- 默认 `ARC_HARNESS_MODE=schema`；旧 FSM 路径保留为 `harness_mode=fsm` 消融
- Baseline 仍禁止可执行 WM / BFS

验证：`pytest` 27 passed；`ruff` 通过；`mock-ab`（schema）玩具环境可过关。

### Schema v2 真实 pilot（DeepSeek v4-pro，non-thinking）

- Phase 0（`pilot-runs/20260722T030849.156866Z`，8 act）：paired_valid；
  harness 写出 `world_model.py`，有 planned commit 但预测 mismatch；
  工具参数兼容性随后已加固（`source`/`code`、整型 action id）。
- Phase 1（`experiment-runs/20260722T031809.365218Z`，50 act，timeout 1200s）：
  - Baseline：50/0lv，~$0.028，66s
  - Harness：50 explore / 0 planned / 0lv；`run_backtest` **2 次全绿**；
    多次 `commit_actions(exploration)`；~$0.174，1115s；paired_valid
  - 目标 `levels_completed>=1`：仍未达成（模型机制假设尚不足以 BFS 到真 goal）

机制对齐进度：已出现「写代码 → 全历史 backtest 绿」轨迹；能力过关仍依赖更强
`step()`/`is_goal` 质量与更少 JSON 截断。

## Sol 接近 Schema（2026-07-22）

已实现更接近 Schema 的工程层：

- 通用 OpenAI 兼容客户端（DeepSeek / `gpt-5.6-sol`）
- `apply_patch` 增量改 `world_model.py`（避免整文件塞进 JSON）
- `last_mismatch` 结构化反馈进 deliberation
- `ARC_MAX_SPEND_USD` 硬花费封顶；`ARC_MODEL_PROVIDER=openai` 一键切 Sol
- 默认加长 deliberation / plan depth / planner nodes

**预算判断（重要）**：`$10` **不够**复现 Schema 级效果（Sol 约 `$5/$30` per MTok；
Schema 单局常需数百环境步 + xhigh）。详见 [`docs/sol-budget.md`](sol-budget.md)。

合理预算建议：
- ls20 认真冲 `levels_completed>=1`：`$30–80`
- 单局接近人效：`$100–300`
- Public 多游戏：`$1000+`

在 `$10` 内只建议：medium effort + `ARC_MAX_SPEND_USD=8` + 短 pilot。
