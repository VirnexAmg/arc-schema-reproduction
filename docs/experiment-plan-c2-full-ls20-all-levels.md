# C2: Codex Plus Full Harness / ls20 全关卡预注册

## 目标与范围

本轮只运行一个 Full Schema-style harness，不运行 baseline 或组件消融。
目标是从全新 seed=0 episode 开始，尽可能完成 `ls20-9607627b` 的全部
7 个 levels。达到 Level 7 / WIN 时立即停止。

本轮是单条件能力实验，不单独产生新的因果 completion-gap 结论。它与此前
seed=0 的 18-call harness/baseline pair 可作历史参照，但预算不同。

## 固定运行条件

- runtime: `codex_cli` 0.146.0
- model: `gpt-5.6-sol`
- reasoning effort: `xhigh`
- thinking mode: `disabled`
- game: `ls20`
- schema seed: `0`
- runs: `1`
- agent: `harness`
- harness mode: `schema`
- target levels: `7`
- `schema_commit_only=true`
- `allow_approximate_visual_matches=true`
- `codex_compound_cycle=true`
- vision flag on；每轮最新 PNG 必须通过 Codex CLI `--image` 实际附加，
  并在工作区 `vision-inputs/` 留下内容寻址副本

## 资源上限

- environment actions: 800
- logical Codex/model calls: 72
- run timeout: 21,600 seconds（6 小时）
- total tokens: 14,000,000
- uncached prompt tokens: 4,500,000
- output tokens: 1,200,000
- per-call total-token reserve: 600,000
- notional proxy: USD 75
- `ARC_MAX_SPEND_USD=0`
- `ARC_EXPERIMENT_MAX_SPEND_USD=0`

Codex Plus 不按 notional proxy 结算。启动前 Plus 7-day 窗口剩余 79%，无
额外 credits 或 reset credits。运行期间只读监控剩余额度；若降到 15% 安全
储备线，不再追加任何实验，并优先让当前已开始的模型 turn 自然完成后停止。

## 停止条件

按优先级：

1. `levels_completed >= 7` / WIN；
2. 任一动作、调用、token、notional 或 6 小时墙钟上限；
3. ARC terminal；
4. 首次不可恢复的 Codex/网络/协议基础设施失败（fail fast，不自动长跑重试）；
5. 视觉附件未进入 CLI 命令或未在工作区落盘。

## 启动前代码指纹

- git HEAD: `68cb783914364a2922afa368af7d2fe3c0e72ee1`（工作树包含已批准的未提交修正）
- `config.py`: `a390f52232b75937d4c8302d9279f3183cd64c819036d2c3e1a44a8849503fe0`
- `cli.py`: `9e2d51eb31f2e03a396c9d2ff585572ec71d754392e04e31cfb72f52ca464cd9`
- `codex_cli_client.py`: `9581132e52cad972c31e29f84cb9e0b9ecf89fbf379992f464c074750a05d99c`
- `runner.py`: `74d4a1e1912cb0837328a863a6ef69c73aad0ca95a035e3f3accb080b24d8ed5`
- `deliberation.py`: `6e1b4c89cd4c22d6a67fc1c6f0dca9b84e1511068c953cd5156423f48195aed9`
- `program_world_model.py`: `d911e914778067523ec7947576cebb5712ea914e46c31b4b822e7f8dde0dd1b5`
- `workspace.py`: `75d277e6c1883804e798fb2b20d06a6122f20f2dc84857480b6f3cdb81563432`
- `test_codex_cli_runtime.py`: `e7d6b9ba585c4c7f3b321bed4822cd00c717d62c67b4866c8c6b8f3d31c2f59e`
- verification: `pytest` 85 passed；`ruff check src tests` passed；真实 PNG 冒烟通过

## 只读审计

结束后审计 `experiment.json`、`harness-run-0.jsonl`、`trace_index.md`、
`codex-cli-events.jsonl`、`vision-inputs/`、notes/notes_history、
world_model/wm_versions 和 hypotheses ledger。报告逐 level checkpoints、动作构成、
调用与 session rollover、tokens/notional、网络事件、模型/笔记/假说质量及停止根因。
