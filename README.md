# ARC Schema Reproduction

Codex-hosted runs use an explicit, auditable context policy. The main default is
one continuing thread per game/run; see
[`docs/codex-context-policies.md`](docs/codex-context-policies.md) for the
`persistent`, `adaptive`, and `fixed_turns` treatments.

一个面向 ARC-AGI-3 的最小 Schema-like agent harness，用统一环境适配器对比：

- `baseline`：每个真实步骤直接由同一模型选择一个合法动作；
- `harness`：模型生成受限声明式状态机，历史回放通过后才允许 BFS
  规划，并在每个真实步骤后严格核对预测。

第一阶段只验证机制和实验可重复性，不代表已经证明 harness 能涨分。

## 安装

```powershell
uv sync --dev
Copy-Item .env.example .env
```

必须把 `DEEPSEEK_MODEL` 设置为供应商实际提供的精确 model ID；代码不会猜测
或硬编码 `DeepSeek-v4-pro` 的 ID。API key 只从 `DEEPSEEK_API_KEY` 读取，
不会写入配置快照或日志。

## 无 API 成本验证

```powershell
uv run pytest -q
uv run ruff check .
uv run arc-schema mock-ab --runs 2 --max-actions 2
uv run arc-schema arc-smoke --max-actions 1
```

`mock-ab` 完整运行 baseline/harness 并保存 `experiment.json` 和每次运行的
哈希链 JSONL。`arc-smoke` 使用本地缓存的真实 `ls20`，执行一个动作，但不调用
DeepSeek。

## 受控真实 A/B smoke test

先只查看调用范围，不会触发模型 API：

```powershell
uv run arc-schema real-ab --runs 1 --max-actions 2
```

确认终端显示的逻辑调用/API 重试上界和成本风险后，再显式执行：

```powershell
uv run arc-schema real-ab --runs 1 --max-actions 2 --confirm-api-cost-risk
```

默认 `ARC_OPERATION_MODE=offline`，因此使用缓存的 ARC 游戏；DeepSeek 仍会联网。
若未配置单价，成本字段保留为 `null`，不会伪造估算。

## 实验输出

每个实验目录包含：

- `experiment.json`：脱敏配置、逐次结果、均值、样本标准差和完成率；
- `baseline-run-N.jsonl` / `harness-run-N.jsonl`：模型请求与原始响应、
  observation、action、transition、backtest、计划和失败记录；
- 每条 JSONL 记录链接前一条的 SHA-256，可检测事后篡改。

哈希链只是 tamper-evident：有本机文件写权限的人仍可重写整条链。严肃实验应将
日志同步到签名或 WORM 存储。

## 安全边界

模型输出不会作为 Python 执行。world model 只能声明有限状态、精确 observation
快照和动作转移；本地解释器负责 backtest 与有界 BFS，因此模型没有文件或网络
访问能力。当前实现尚未提供通用 Python sandbox，也不接受生成代码。
