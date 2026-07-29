# Trace index (auto-generated)

- agent: `harness`
- status: `failed`
- levels_completed: 1
- environment_actions: 270
- journal: `experiment-runs/20260728T151714.012744Z/harness-run-0.jsonl`
- workspace: `experiment-runs/20260728T151714.012744Z/workspace-harness-0`
- notes.md: `experiment-runs/20260728T151714.012744Z/workspace-harness-0/notes.md` (notes_version=39)
- world_model.py: `experiment-runs/20260728T151714.012744Z/workspace-harness-0/world_model.py` (wm_version=118)
- wm_versions/: `experiment-runs/20260728T151714.012744Z/workspace-harness-0/wm_versions`
- notes_history/: `experiment-runs/20260728T151714.012744Z/workspace-harness-0/notes_history`
- notes_revision events: 39
- wm_revision events: 117
- reasoning_status present/tokens_only: 0/366

## Sample jump points

- seq=18 deliberation_started env_step=8 vision=True certified=False
- seq=21 notes_revision v1 env_step=8 preview='# Working notes\n\n## Objects\n- 64x64 scene with a 5x5 moving token. Its normal sp'
- seq=26 wm_revision v2 kind=write_code path=experiment-runs/20260728T151714.012744Z/workspace-harness-0/wm_versions/v0002.py
- seq=35 wm_revision v3 kind=apply_patch path=experiment-runs/20260728T151714.012744Z/workspace-harness-0/wm_versions/v0003.py
- seq=2390 wm_revision v111 kind=apply_patch path=experiment-runs/20260728T151714.012744Z/workspace-harness-0/wm_versions/v0111.py
- seq=2395 wm_revision v112 kind=apply_patch path=experiment-runs/20260728T151714.012744Z/workspace-harness-0/wm_versions/v0112.py
- seq=2404 wm_revision v113 kind=apply_patch path=experiment-runs/20260728T151714.012744Z/workspace-harness-0/wm_versions/v0113.py
- seq=2413 wm_revision v114 kind=apply_patch path=experiment-runs/20260728T151714.012744Z/workspace-harness-0/wm_versions/v0114.py
- seq=2422 wm_revision v115 kind=apply_patch path=experiment-runs/20260728T151714.012744Z/workspace-harness-0/wm_versions/v0115.py
- seq=2427 wm_revision v116 kind=apply_patch path=experiment-runs/20260728T151714.012744Z/workspace-harness-0/wm_versions/v0116.py
- seq=2432 wm_revision v117 kind=apply_patch path=experiment-runs/20260728T151714.012744Z/workspace-harness-0/wm_versions/v0117.py
- seq=2441 wm_revision v118 kind=apply_patch path=experiment-runs/20260728T151714.012744Z/workspace-harness-0/wm_versions/v0118.py

## How to spot-check

1. Open `notes.md` and `notes_history/` for hypothesis text.
2. Diff `wm_versions/vNNNN.py` around a `wm_revision` seq above.
3. In the jsonl, search `"event":"deliberation_turn"` or `"event":"model_response"`.
4. If `reasoning_status` is `tokens_only`, the channel billed reasoning tokens but returned no text.
