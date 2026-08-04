# C3: Codex Plus Batched Direct Baseline / ls20 全预算预注册

## 研究问题

本轮只运行一条 batched direct baseline，不追加 harness、旧式逐动作 baseline 或其他
消融。它与既有 Full Schema harness 实验
`20260801T075813.339305Z` 构成同模型、同 seed、同全局资源上限的配对对照。

主要问题是：在不提供 Schema workspace、可执行世界模型、notes、hypothesis ledger、
replay/backtest、BFS/search、certification gate 或自动纠错的前提下，仅把 direct
baseline 从“一次调用一个动作”提升为“一次调用可提交 1--16 个动作”，能否达到
Full harness 已取得的 2 levels。

这是单 seed 的描述性 paired completion-gap 检验，不是多 seed 的统计证明。实验结束后
不得把动作上限事后改为 Full harness 实际消耗的 496，也不得根据结果追加第二次长跑。

## 固定 treatment

- runtime: `codex_cli` 0.146.0
- model: `gpt-5.6-sol`
- reasoning effort: `xhigh`
- thinking mode: `disabled`
- vision: on；每次调用附加当前最新 PNG，并在运行目录 `vision-inputs/` 留下副本
- game: `ls20`
- seed: `0`
- runs: `1`
- agent/result label: `baseline`
- direct baseline batch cap: `ARC_BASELINE_MAX_BATCH_ACTIONS=16`
- 每次模型调用必须返回 1--16 个动作；不确定时允许只返回 1 个
- 批内动作按顺序、开环执行，不向模型提供中间观察
- `RESET(0)` 不允许由模型提交；GAME_OVER 后只允许外层 runner 自动 reset
- batch 在 level boundary、GAME_OVER/WIN、动作/墙钟/token/notional terminal 处立即截断
- 普通撞墙或画面变化不截断 batch，因为该 treatment 没有预测器
- malformed JSON、错误顶层 schema、空 batch、超过 16 个动作、非法动作或协议违规
  均 fail fast；batched treatment 不使用 fallback action
- persistent Codex conversation memory 允许保留；每 4 turns 或 prompt rollover 条件触发
  新 thread，与 Full harness 的传输配置一致
- 禁止本地文件/仓库/游戏源码/网络读取和 shell/tool 调用；Codex sandbox 为 read-only

为了保持 CLI 和历史聚合兼容，本 treatment 仍以 `--agents baseline` 运行；
`experiment.json.config.baseline_max_batch_actions=16`、batch journal events 和新增 metrics
负责把它与 legacy one-action baseline 区分。

## 固定实验配置

- `ARC_AGENT_RUNTIME=codex_cli`
- `ARC_GAME_ID=ls20`
- `ARC_SCHEMA_SEEDS=0`
- `ARC_RUNS=1`
- `ARC_HARNESS_MODE=schema`（仅为共享主线预检配置；baseline 不获得 Schema 能力）
- `ARC_TARGET_LEVELS_COMPLETED=7`
- environment actions: `800`
- logical model calls: `72`
- run timeout: `21,600` seconds
- total tokens: `14,000,000`
- uncached prompt tokens: `4,500,000`
- output tokens: `1,200,000`
- per-call total-token reserve: `600,000`
- notional proxy: USD `75`
- `ARC_MAX_SPEND_USD=0`
- `ARC_EXPERIMENT_MAX_SPEND_USD=0`
- `ARC_MAX_GAME_OVER_RESETS=10`
- `ARC_SCHEMA_COMMIT_ONLY=true`
- `ARC_ALLOW_APPROXIMATE_VISUAL_MATCHES=true`
- `ARC_CODEX_COMPOUND_CYCLE=true`
- `ARC_DELIBERATION_MAX_TURNS=2`
- `ARC_CODEX_MAX_TURNS_PER_THREAD=4`
- `ARC_CODEX_ROLLOVER_PROMPT_TOKENS=450000`
- `ARC_CODEX_CLI_TIMEOUT_SECONDS=3600`
- model context transitions: `16`
- model baseline max output setting: `2048`

Codex Plus 不按 notional proxy 结算；动作、调用、token、notional、墙钟共同限流。
启动前重新读取 Plus 7-day 剩余额度；15% 为不追加实验安全线，不中断一个已经自然开始的
turn。额度查询本身不调用模型。

## 固定停止条件

按优先级：

1. `levels_completed >= 7` / WIN；
2. 800 environment actions；
3. 72 logical model calls；
4. 任一 token/notional 上限或 21,600 秒墙钟上限；
5. ARC terminal 且不能在 reset 上限内继续；
6. 首次不可恢复的 Codex/ARC/网络/视觉附件/协议基础设施失败，fail fast，不自动重跑。

## 配对解释规则

固定 comparator 是 `20260801T075813.339305Z`：seed 0、72 calls、800-action cap，
Full harness 完成 2 levels，实际 496 environment actions，因 model-call budget 停止。

- batched baseline `< 2 levels`：记录为该 seed、该预算下的 observed paired completion gap，
  且已排除“baseline 每调用只能做一步”这一主要混杂；不外推为跨 seed 统计结论。
- batched baseline `>= 2 levels`：不能再把既有差异归因于 Schema；结果支持 batching/call
  efficiency 至少足以消除此前 gap。
- 任一基础设施或协议失败：该 run 对能力比较无效，不按 0-level 能力样本解释。

## 启动前代码指纹与验证

- git HEAD: `68cb783914364a2922afa368af7d2fe3c0e72ee1`（工作树含用户已批准的未提交修正）
- `agents.py`: `f5df03faca5d8ff551c77813e970f3d4b0fd0ba84aec6bc3a89308d20fa66d0e`
- `runner.py`: `ba0ebbbda44465912467a7d9c8cbc578e4c77b3960ec70c8851285766948fc70`
- `config.py`: `d559fa8fad37cdf8b63397c1fbd2c7115e1b84dabe39a6811e3c67d9f74e9e70`
- `core.py`: `7d8d70057c1c15a25ed0709210991434f8f77933bbe8280415ce86a64dfef00f`
- `evaluation.py`: `84dd41c4f69188b2df9554e19f917bdb912355567bb57a72bc361529d4fe9128`
- `cli.py`: `26d9913b0eb14ad4fff4f858a67b7d318ea00f27f5f97d08f7b2b6f8cd45c965`
- `codex_cli_client.py`: `8523962a9e3c77e3981933276167631faf59c36ffd196edc487c60cb74fe9f9e`
- `test_evaluation.py`: `ec71cd555cd6f222c17250413ecf9192ca68e6e953019ce3c454b8c5b6801c3f`
- `test_codex_cli_runtime.py`: `3e21aad79d47ee4c8f9d41fb5aebe68a9f6a40d22c555e67d1879c975c2f9a56`
- 新增核心定向测试：5 passed
- 全量回归：89 passed；唯一沙箱内失败为既有 Windows 子进程退出 `<2s` 时序断言，
  同一用例在非受限进程环境复跑 passed
- `ruff check src tests`: passed

## 结束后只读审计

审计 `experiment.json`、`baseline-run-0.jsonl`、`codex-cli-events.jsonl`、
`vision-inputs/`，并统计 batch size 分布、proposed/executed/truncated actions、动作构成、
level checkpoints、调用与 session rollover、tokens/notional、网络/协议事件、停止根因。
Baseline 不应产生 Schema `trace_index.md`、notes/notes_history、world_model/wm_versions 或
hypotheses ledger；若出现这些产物，视为 treatment contamination。
