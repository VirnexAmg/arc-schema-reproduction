# B4′ 预注册实验方案：ls20 completion gap

日期：2026-07-29  
状态：已执行一次 harness-only screening；结果为负，未启动 baseline。

> 执行前用户将单局/实验花费上限由本文原定的 25 USD 明确提高为 30 USD；
> 其余主指标与条件式 baseline 规则不变。

## 目标与主指标

阶段目标不是“同为 L1 但少走几步”，而是在相同环境动作上限下得到：

- harness `levels_completed >= 2`；
- baseline `levels_completed <= 1`；
- 因此 `harness_levels - baseline_levels >= 1`。

主指标是 `levels_completed` 差值。环境动作数、费用、模型调用、RHAE/每关动作数是次指标，
不能替代 completion gap。

## 固定条件

正式 ls20 Schema 主线必须同时满足：

- Provider 路径：Inferera / OpenAI-compatible；
- model：`gpt-5.6-sol`；
- `reasoning_effort=medium`；
- `thinking_mode=disabled`；
- vision enabled；
- `harness_mode=schema`；
- 单 agent 正花费上限与每请求预留均大于 0；
- 不读取游戏源码，不向 prompt / helper / world model 注入关卡答案；
- `.env` 不进入 Git。

CLI 会在正式 ls20 Schema 运行前检查这些条件。先去掉
`--confirm-api-cost-risk` 执行命令，只打印预检信息，不调用 API。

## 阶段 1：B4′ harness-only screening

一次运行，不做并行 A/B：

- seed：0；
- 环境动作上限：220；
- 单局花费上限：25 USD；
- 实验总花费上限：25 USD；
- 每请求预算预留：0.75 USD；
- model calls 上限：沿用显式配置；
- vision：on。

固定模型/provider/vision 项应已存在于本地 `.env`（密钥不打印、不提交）；CLI 会在付费调用
前核验。动作与花费预算使用命令行显式覆盖，避免旧 `.env` 数值影响本次预注册范围：

```powershell
uv run arc-schema real-ab --agents harness --runs 1 --max-actions 220 `
  --max-spend 25 --experiment-max-spend 25 --request-spend-reserve 0.75
```

最后一行不带确认参数，只做零费用预检。用户明确批准后，才可增加
`--confirm-api-cost-risk`。

### B4′ 停止规则

- 达到 L2：立即视为 screening 成功；不擅自追加第二次 harness。
- 220 actions / 25 USD / model-call / wall-clock 任一先到：停止。
- 若无 L2：先做离线轨迹审计，不原样重跑、不提高 effort、不扩大预算。
- GAME_OVER 可按既有上限自动 RESET，但必须保留同一 Timeline、notes 与 WM。

### B4′ 机制证据门槛

L2 只是能力门槛；同时检查：

- 所有 planned 动作均有 `plan_id`，且
  `bfs_derived_planned_actions == planned_actions`；
- 有动作前 `prequential_prediction`，而非只靠事后 backtest；
- notes 中有命名假说、相互区分的预测、证据 sequence 与被排除项；
- `experiment_proposed` 的 action 与后续 `experiment_id` commit 一致；
- WM 表达可复用对象/变换/状态，不是整关 RLE、坐标表或步数特判；
- `trace_index.md` 能跳到 level boundary、回测、BFS、commit、mismatch、
  notes/WM 修订与视觉帧。

## 阶段 2：条件式 baseline

仅当 B4′ 达到 L2 后执行。固定同一个 seed、模型、effort、thinking、vision 与
220 环境动作上限：

- baseline 单局花费上限：25 USD；
- 实验总花费上限：25 USD；
- 不允许 baseline 使用可执行 WM、BFS 或多动作计划；
- 不因看到 harness 路径而修改 baseline prompt。

零费用预检命令：

```powershell
uv run arc-schema real-ab --agents baseline --runs 1 --max-actions 220 `
  --max-spend 25 --experiment-max-spend 25 --request-spend-reserve 0.75
```

用户再次明确批准后才增加确认参数。

这个 outcome-contingent baseline 用于省预算的探索性 completion-gap 证据；它不是统计上
充分的最终结论。

## 阶段 3：确认性配对（后续、另行审批）

只有探索性 gap 已出现且有新增预算时再做：

- 预先固定 2 个独立 seed；
- 每个 seed 同时跑 baseline/harness；
- 同一动作上限为主比较，同花费上限为补充比较；
- 实验总花费上限至少覆盖双方，但仍保留请求预留；
- 任何无效 pair（超时、基础设施错误、不等花费提前停）不计入能力差值。

## 每次交付必须报告

- `experiment_id`；
- 两侧 `levels_completed`、每关首次 level-up action、总 actions；
- 单侧与实验总花费；
- model calls / failures；
- BFS 计划数、BFS-derived planned 比例；
- prequential predictions / matches / mismatches；
- 假说实验数量与 notes/WM 质量判断；
- `trace_index.md`、journal、notes_history、wm_versions、vision_frames 抽查路径；
- 是否出现 L2、是否形成 completion gap；
- 下一步是停止、离线修 harness，还是申请确认性配对预算。

## B4′ 实际结果与协议偏差

- experiment_id：`20260729T043320.478531Z`
- harness：0 level / 220 actions / 500 logical model calls；
- 正式实验估算费用：19.022161 USD（另有 vision smoke 约 0.00275 USD）；
- 500 responses、501 API attempts、0 model failures；
- 2 个 BFS plans、11/11 planned actions 来自 BFS；
- prequential：207 predictions / 183 matches / 24 mismatches；
- 104 个实验提案、32 版 notes、94 版 WM；
- 未出现 L1/L2，因此按预注册条件没有运行 baseline。

协议偏差：模型调用预算在 env step 150 首次耗尽，但旧 runner 把
`model_call_budget` 当作普通 no-commit，继续执行了 70 个 forced-explore actions，
最后错误标记为 `action_budget_exhausted`。因此“有模型参与的有效段”只到 step 150；
后 70 步只能作为基础设施缺陷证据，不能算 Schema 推理样本。

离线修复要求：

- `model_call_budget` 必须立即终止并记录准确状态；
- 持久化假说 lineage 与实验 outcome，但不得因理论整理阻塞目标导向行动；
- 对 WM 实施描述长度/AST/分支软正则；仅极端膨胀和轨迹查表硬拒绝；
- 允许小范围非终局视觉误差作为 approximate match，完成边界仍严格；
- deliberation 由 mismatch、未解析实验结果和认证状态触发，并按剩余调用/动作预算
  自适应限制工具轮次；
- 修复与离线回归通过前，不申请下一次付费实验。
