# Codex Plus xhigh / ls20 L2 预注册实验方案

## 科学问题

主问题不是“同一 level 少走几步”，而是：持久化、可执行世界模型的
Schema-style harness 能否让 `gpt-5.6-sol` 完成至少 2 个 ls20 levels。

本轮只跑 harness，不声明 completion gap。只有 harness 达到
`levels_completed >= 2` 后，才补同模型、同 seed、同资源上限的无 harness
baseline。

## 与 B4/B5 相比的关键改变

- 单个 Codex CLI 编码代理线程贯穿整个 run，不再每轮把模型当作无工具的
  JSON 聊天端点。
- Codex 可直接查看当前 PNG，并原生编辑 `world_model.py` 与 `notes.md`；
  harness 验证、版本化并可恢复非法编辑。
- 全 Timeline 回放分成两级认证：小范围、非终局视觉误差可得到
  navigation-only 近似认证；BFS/planned 必须是全历史精确认证。level 边界、
  WIN/GAME_OVER 与动作空间始终严格，因为下一 level 的初始帧来自真实环境。
- 真实动作全部由 agent 的 `commit_actions` 提交。关闭冷启动强制探索、
  无提交 fallback 和 idle burst，避免 harness 替模型盲走。
- 世界模型允许 NumPy、较大的程序和学到的坐标/图案常量；这些会被审计，
  但不因复杂本身拒绝。导入、网络/文件访问和 dunder 仍被沙箱禁止。
- 到达 L2 目标立即停止，并在每次 level-up 记录 actions、Codex turns 与
  tokens 快照。

## C0：不碰 ARC 动作的运行前检查

必须全部通过才允许 C1：

1. 当前用户会话中 `codex --version` 可执行且已登录 Codex Plus。
2. 一次临时 workspace 调用能产生 `thread.started`，随后能用
   `codex exec resume` 继续同一 thread。
3. 启动参数明确包含 `gpt-5.6-sol` 和 `model_reasoning_effort="xhigh"`。
4. Codex 能读取测试 PNG、编辑测试版 notes/world model，并返回一个合法
   JSON tool command。
5. `codex-cli-events.jsonl`、notes 历史和 world-model 历史均落盘。

C0 会消耗少量 Codex Plus 配额，但不执行 ARC 环境动作；仍需用户单独批准。

## C1：harness-only，目标 L2

建议配置：

```dotenv
ARC_AGENT_RUNTIME=codex_cli
DEEPSEEK_MODEL=gpt-5.6-sol
DEEPSEEK_REASONING_EFFORT=xhigh
DEEPSEEK_VISION_ENABLED=true

ARC_GAME_ID=ls20
ARC_SCHEMA_SEEDS=0
ARC_RUNS=1
ARC_HARNESS_MODE=schema
ARC_SCHEMA_COMMIT_ONLY=true
ARC_ALLOW_APPROXIMATE_VISUAL_MATCHES=true
ARC_TARGET_LEVELS_COMPLETED=2

ARC_MAX_ENVIRONMENT_ACTIONS=160
ARC_MAX_MODEL_CALLS_PER_RUN=12
ARC_DELIBERATION_MAX_TURNS=2
ARC_RUN_TIMEOUT_SECONDS=10800
ARC_WM_TIME_RESERVE_SECONDS=120
ARC_MAX_TOTAL_TOKENS_PER_RUN=4000000
ARC_MAX_UNCACHED_TOKENS_PER_RUN=1250000
ARC_MAX_OUTPUT_TOKENS_PER_RUN=250000
ARC_TOKEN_RESERVE_PER_CALL=600000
ARC_MAX_NOTIONAL_COST_USD=15
ARC_CODEX_MAX_TURNS_PER_THREAD=4
ARC_CODEX_ROLLOVER_PROMPT_TOKENS=450000
ARC_CODEX_COMPOUND_CYCLE=true

# Codex Plus 不按本仓库的 API 美元估价；美元 cap 对 CLI 不生效。
ARC_MAX_SPEND_USD=0
ARC_EXPERIMENT_MAX_SPEND_USD=0
```

命令（只在 C0 通过且用户明确批准后执行）：

```powershell
uv run arc-schema real-ab --agents harness --runs 1 --max-actions 160 `
  --max-model-calls 12 --run-timeout 10800 --confirm-api-cost-risk
```

停止条件按优先级为：

1. `levels_completed >= 2`（成功，立即停）；
2. 160 个环境动作；
3. 12 个 Codex turns；
4. 4,000,000 总 tokens、1,250,000 uncached prompt tokens、250,000 output tokens；
5. 3 小时墙钟；
6. terminal / 无法恢复的运行错误。

Codex CLI 若不报告 token usage，第 4 项无法单独形成硬保证；动作、turn 和
墙钟上限仍是硬边界。

## C1 判定与抽查

主要终点：`levels_completed >= 2`。次要指标按每个 level 单独报告：

- 环境动作数；
- Codex turns；
- prompt / cached / output / reasoning / total tokens（CLI 可提供时）；
- exact backtest 的 checked 数、首次 mismatch；
- notes、hypothesis ledger 和 world model 的版本演化；
- BFS / navigation / exploration 构成。

必须抽查：

- `workspace-harness-0/trace_index.md`
- `workspace-harness-0/codex-cli-events.jsonl`
- `workspace-harness-0/notes.md` 与 `notes_history/`
- `workspace-harness-0/world_model.py` 与 `wm_versions/`
- `workspace-harness-0/hypotheses.json` 与 `hypothesis_versions/`
- `harness-run-0.jsonl`

暂时错误但能指导通关的理论是合格中间产物；失败判据是不能解释已见证据、
不能产生有价值行动或妨碍后续 level 修订，而不是“没有猜中唯一真机制”。

## 达到 L2 后的 completion-gap 配对

再实现并运行一个 Codex CLI direct-action baseline：

- 同一个 `gpt-5.6-sol xhigh`；
- 同 seed=0、视觉输入、160 actions、12 turns 与相同多维 token/墙钟上限；
- 允许持久对话，但没有可执行 world model、严格 replay、BFS、认证门禁和
  harness 工作区；
- 预先固定 prompt 与停止条件。

只有 `harness levels > baseline levels`，或 harness 达到目标而 baseline
在等资源上限内未达到，才称为 completion gap。旧的 Inferera/API baseline
只能作历史参照，不能单独支持 Codex Plus harness 的因果结论。
