# Codex context policies

Updated: 2026-08-08

This document defines the context treatment for Codex-hosted ARC-AGI-3 runs.
It changes runtime/context management only; it does not contain new benchmark
results.

## Experimental unit

Every `(harness, game, run, seed)` gets its own active Codex thread. Threads are
never shared across games, runs, seeds, or treatments. A rolled-over thread is
not resumed later: recovery always moves forward from the current workspace
checkpoint.

## Policies

### `persistent` (main experiment default)

- Keep one continuing thread across model calls and level boundaries.
- Ignore fixed-turn and prompt-watermark rollover settings.
- Persist a workspace checkpoint at every level boundary.
- Roll over only after an explicit protocol, runtime, timeout, shell-context, or
  context-length failure.

### `adaptive`

- Keep the current thread under the soft prompt-token watermark.
- On the first soft-watermark crossing in a thread generation, persist a
  checkpoint but keep the thread.
- At the hard watermark, persist another checkpoint and schedule a one-way
  rollover before the next deliberation episode.
- Level boundaries checkpoint without rolling over by default.

### `fixed_turns` (ablation)

- Schedule rollover after `ARC_CODEX_MAX_TURNS_PER_THREAD` successful model
  calls in the current thread.
- Prompt watermarks do not alter this treatment.
- Level boundaries checkpoint without rolling over by default.

Set `ARC_CODEX_ROLLOVER_ON_LEVEL_BOUNDARY=true` only to reproduce the legacy
level-boundary behavior; it is not part of the main treatment.

## Configuration

```dotenv
ARC_CODEX_CONTEXT_POLICY=persistent
ARC_CODEX_MAX_TURNS_PER_THREAD=4
ARC_CODEX_SOFT_CONTEXT_PROMPT_TOKENS=220000
ARC_CODEX_HARD_CONTEXT_PROMPT_TOKENS=350000
ARC_CODEX_ROLLOVER_ON_LEVEL_BOUNDARY=false
```

`ARC_CODEX_ROLLOVER_PROMPT_TOKENS` remains a read-only environment fallback for
old configurations. New runs serialize the explicit soft and hard fields.

The adaptive watermarks compare against the latest Codex turn's reported input
tokens, which are the closest observable proxy for current context pressure.
They do not use run-wide cumulative prompt usage, because that would repeatedly
count retained history and trigger rollovers even when the active context is
still healthy. Cumulative usage remains recorded separately in run metrics.

## Checkpoints and audit events

Each checkpoint is stored under the run workspace:

```text
context_checkpoints/checkpoint-NNNN/
  manifest.json
  world_model.py       # Schema runs
  notes.md             # Schema runs
  hypotheses.json      # Schema runs
```

The manifest records the policy, reason, thread prefix, session generation,
turn count, latest prompt/cache usage, timestamp, and SHA-256 for every copied
state file. The hash-chained run journal records the same checkpoint as a
`codex_context_checkpoint` event.

Rollover reasons are intentionally disjoint:

- `fixed_turn_limit`
- `prompt_hard_watermark`
- `context_length_error`
- `codex_turn_error`
- `codex_timeout`
- `protocol_error`
- `shell_tool_context`
- an explicitly requested recovery reason

Soft checkpoints use `prompt_soft_watermark`; level checkpoints use
`level_boundary`. Neither implies a rollover.

## Verification boundary

Unit tests and static checks may exercise these policies with fake Codex event
streams and toy environments. They must not call a real model, consume Codex
quota, or run an ARC benchmark unless a later experiment plan explicitly
authorizes it.
