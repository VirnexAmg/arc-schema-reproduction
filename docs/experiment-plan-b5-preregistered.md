# Phase B5 preregistration

Status: completed on 2026-07-29.

## Objective

Screen whether the completion-oriented Schema harness can complete level 2 or
higher on `ls20`. The primary outcome is levels completed. Mechanism
descriptions are instrumental and may remain provisional or even be locally
wrong when they support useful action selection.

## Fixed mainline configuration

- Agent: harness only; no baseline in this spend authorization
- Runs / seed: 1 run, seed 0
- Environment actions: at most 220
- Model calls: at most 700
- Spend: USD 30 per-run hard cap and USD 30 experiment hard cap
- Per-request reserve: USD 0.75
- Model provider: OpenAI-compatible Inferera endpoint
- Model: `gpt-5.6-sol`
- Reasoning effort: `medium`
- Thinking mode: `disabled`
- Vision: enabled
- Harness mode: `schema`
- Auto reset after game over: enabled

The run remains fixed at 220 actions so that a successful level transition does
not trigger an outcome-dependent extension. It may continue beyond level 2
within that action and spend envelope because the operational objective is to
complete as many levels as possible.

## Primary and secondary outcomes

1. Primary: maximum `levels_completed`; success threshold is level 2 or higher.
2. Secondary: action index of each level transition and terminal reason.
3. Diagnostics: planned/exploratory action mix, prequential strict and
   approximate matches, backtest results, model-call use, notes and hypothesis
   revisions, world-model revisions, and journal hash verification.

No baseline, second seed, or follow-up run is authorized by this preregistration.
If B5 reaches level 2, a matched baseline requires a separate approval.

## Result

- Experiment ID: `20260729T101629.181203Z`
- Terminal status: `spend_budget`
- Levels completed: 1 of 7
- Level 1 boundary: environment action 108
- Total environment actions: 176
- Model calls / API attempts / failures: 451 / 451 / 0
- Estimated cost: USD 29.307372
- Exploration / planned actions: 176 / 0
- BFS calls yielding plans: 62 / 0
- Prequential predictions: 162, with 156 matches (36 approximate) and 6 mismatches
- Experiments proposed / observed / resolved: 20 / 18 / 16
- Notes / hypothesis-ledger / world-model versions: 12 / 81 / 33
- Journal records: 3271
- Verified terminal journal hash:
  `704882f39a7ba16abacc2b8b2394a8c6bbc3f595aefc01a8098289d0a1bc6d14`

The level-2 threshold was not reached, so no completion gap and no matched
baseline were produced. The run restored level-1 completion after B4's zero-level
result, but the harness did not convert its route knowledge into planned
execution.

The clearest protocol failure was the gap between single-step exploration and
BFS-bound planning. The model made 102 rejected multi-action exploration
commits because exploration accepted exactly one action, while all 62 BFS calls
returned no plan. At the final deliberation it proposed a coherent 12-action
route toward the leading level-2 interaction candidate; the harness rejected
the burst, and the next request was blocked because USD 29.307372 plus the
USD 0.75 request reserve exceeded the USD 30 cap.

Token use also grew sharply after the level boundary. Level 1 consumed 278 calls
and USD 14.637206 at an average 16,882 prompt tokens per call. The 68 level-2
actions consumed another 173 calls and USD 14.670166 at an average 27,564 prompt
tokens per call. This makes context compaction and a monitored navigation-burst
channel higher-priority than merely increasing the next spend cap.
