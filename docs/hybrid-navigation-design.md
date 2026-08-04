# Hybrid Schema harness: monitored navigation

Status: implemented locally on `codex/hybrid-navigation`; no paid experiment has
been started with this design.

Reference implementation: branch `codex/reference-68cb783`, worktree
`C:\Users\Virne\Documents\GitHub\arc-schema-reproduction-reference-68cb783`.

## Why this hybrid exists

The pushed `68cb783` harness allowed any certified model-generated action burst
to be labelled `planned`. That was useful for level progress, but it did not
prove that the route came from the program world model or BFS.

The stricter B4/B5 harness required every planned burst to match the current BFS
plan exactly. This improved provenance but created a deadlock when the agent
could describe a useful route to an interaction before it knew the final level
goal. Exploration remained single-step, so useful multi-step navigation had no
legal execution channel.

The hybrid keeps both scientific distinctions:

- `planned`: exact, current BFS plan with `plan_id`;
- `navigation`: model-proposed 2-to-`max_plan_steps` route toward an interaction
  or subgoal, requiring a certified world model but no BFS goal;
- `exploration`: exactly one action, optionally bound to a registered
  discriminating experiment.

Navigation is not counted as BFS planning. Every navigation step receives a
prequential world-model prediction. The runner stops the remaining burst on a
prediction error/mismatch, illegal action, level boundary, GAME_OVER, WIN,
action/time budget, or spend budget.

## Context and search controls

The full hypothesis ledger remains append-only on disk. The prompt receives a
bounded view:

- at most 12 hypotheses and 6 recent experiments before size trimming;
- no `statement_history`;
- only the latest eight evidence sequence numbers per hypothesis;
- experiment outcomes contain metadata and changed-row counts, not full RLE rows;
- hard prompt-ledger budget of 12,000 serialized characters.

Each deliberation records total context characters and hypothesis-context
characters. Run metrics retain the maximum deliberation context size.

After BFS returns no plan, the workspace records the world-model version, level,
and environment step. Further BFS calls are marked cached during an eight-action
cooldown unless the world model changes. The prompt explicitly directs the
agent to use navigation, revise the model, or explore instead of retrying BFS.

## New audit metrics

- `navigation_actions`
- `bfs_no_plan_results`
- `bfs_no_plan_cache_hits`
- `max_deliberation_context_chars`

Existing `planned_actions` and `bfs_derived_planned_actions` remain strict and
should stay equal for Schema-mode planned execution.

## Local acceptance checks

- Full test suite: 60 passed
- Ruff: passed
- `git diff --check`: passed
- Zero-network mock A/B: passed
- Navigation integration test: a certified two-action navigation burst completes
  the toy level with zero BFS plans
- Mismatch integration test: the burst stops after its first mismatching action
- Context test: lineage and full delta rows remain on disk but are omitted from
  the bounded prompt view

## Paid-run gate

Before another full B5-sized run, use a small explicitly approved pilot and
require all of the following:

1. zero rejected multi-action exploration commits caused by route execution;
2. nonzero `navigation_actions` when the model proposes a coherent route;
3. no immediate repeated BFS calls during a no-plan cooldown;
4. average model calls per environment action below 2.0;
5. average prompt tokens per model call below the B5 value of 20,980, with a
   target below 15,000;
6. no regression in level progress or trace/hash integrity.

Reaching level 2 is still required before authorizing a matched baseline for the
completion-gap experiment.
