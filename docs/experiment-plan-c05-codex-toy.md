# C0.5：Codex xhigh 全闭环验收（ToyEnvironment）

## 目的

C0-R 已证明 Codex CLI 能创建并恢复同一 thread、读取 PNG、编辑 workspace，
但它没有证明真实 runner 能把“编辑世界模型 → 全历史回放 → BFS → 受门禁提交 →
环境反馈 → 轨迹落盘”连成一个闭环。C0.5 专门验证这条链路，不连接 ARC 环境，
因此不能产生 ls20 level，也不能作为 completion-gap 证据。

## 固定条件

- 模型：`gpt-5.6-sol`，`reasoning_effort=xhigh`，vision on；
- 环境：仓库内确定性的 `ToyEnvironment`；
- 最多 4 次 Codex 调用、4 个环境动作、1 小时墙钟；
- 上报资源边界：3,000,000 total、500,000 uncached prompt、100,000 output tokens；
- 每次新调用预留 400,000 total tokens；按配置价格计算的 notional proxy 上限 $5；
- 不使用 `ARC_MAX_SPEND_USD`：Codex Plus 调用不是本进程可结算的 API 美元账单。

这些 token/notional 门禁会阻止“下一次”调用，不能中断已经开始的一次 Codex
调用。因此调用数与墙钟仍是必要的独立边界。

## 通过标准

下列条件必须全部满足：

1. Toy level 完成，且模型调用数在 1–4 次；
2. `world_model.py` 与 `notes.md` 都产生版本化修订；
3. 全历史 backtest `checked > 0` 且为 exact certification；
4. BFS 生成 plan，planned commit 实际执行；
5. 至少一次 prequential prediction match；
6. journal、`trace_index.md` 与原生 `codex-cli-events.jsonl` 均落盘；
7. `c05-report.json` 的 `status` 为 `passed`。

理想结果是 2 次调用：第一次探索，第二次编辑 workspace 后用一个
`schema_cycle` 完成 replay/BFS/commit；4 次是验收硬上限，不是效率目标。

## 命令与授权

不带确认开关只显示风险边界，不调用模型：

```powershell
uv run arc-schema codex-c05 --output c05-validation
```

只有用户针对 C0.5 再次明确批准 Codex Plus 配额后才添加：

```powershell
uv run arc-schema codex-c05 --output c05-validation --confirm-codex-quota-risk
```

C0.5 通过后再单独批准 C1；C0.5 的授权不自动扩展到 ls20。
