# Trace index (auto-generated)

- agent: `harness`
- status: `token_budget`
- levels_completed: 0
- environment_actions: 16
- journal: `experiment-runs\20260801T022435.912080Z\harness-run-0.jsonl`
- workspace: `experiment-runs\20260801T022435.912080Z\workspace-harness-0`
- native Codex events: `experiment-runs\20260801T022435.912080Z\workspace-harness-0\codex-cli-events.jsonl` (when ARC_AGENT_RUNTIME=codex_cli)
- notes.md: `experiment-runs\20260801T022435.912080Z\workspace-harness-0\notes.md` (notes_version=10)
- hypotheses.json: `experiment-runs\20260801T022435.912080Z\workspace-harness-0\hypotheses.json` (hypothesis_version=11)
- world_model.py: `experiment-runs\20260801T022435.912080Z\workspace-harness-0\world_model.py` (wm_version=9)
- wm_versions/: `experiment-runs\20260801T022435.912080Z\workspace-harness-0\wm_versions`
- notes_history/: `experiment-runs\20260801T022435.912080Z\workspace-harness-0\notes_history`
- hypothesis_versions/: `experiment-runs\20260801T022435.912080Z\workspace-harness-0\hypothesis_versions`
- vision_frames/: `experiment-runs\20260801T022435.912080Z\workspace-harness-0\vision_frames`
- notes_revision events: 10
- wm_revision events: 8
- reasoning_status present/tokens_only: 0/11
- level_resource_checkpoints: []
- BFS plans / BFS-derived planned actions: 1/1
- navigation actions: 7
- BFS no-plan results/cache hits: 6/3
- prequential predictions/matches/mismatches: 15/11/4
- prequential approximate matches: 0
- discriminating experiments: 0
- experiments observed/resolved: 0/0
- event-driven deliberations: 12
- max deliberation context chars: 20574
- Codex transport reconnects / HTTPS fallbacks / timeouts / turn failures: 2/0/0/0
- model budget exhausted at action: None

## Level progress and boundaries

- seq=3 vision_frame env_step=0 sha256=c4c421ed71ec path=experiment-runs\20260801T022435.912080Z\workspace-harness-0\vision_frames\env-0000-aa5162a89ba4.png
- seq=17 vision_frame env_step=1 sha256=c092df09caff path=experiment-runs\20260801T022435.912080Z\workspace-harness-0\vision_frames\env-0001-35e6d552a3e8.png
- seq=34 vision_frame env_step=2 sha256=63e3f26b02cc path=experiment-runs\20260801T022435.912080Z\workspace-harness-0\vision_frames\env-0002-a56d194d7a0e.png
- … 4 omitted …
- seq=131 vision_frame env_step=11 sha256=a51c4d6fcddb path=experiment-runs\20260801T022435.912080Z\workspace-harness-0\vision_frames\env-0011-46ea005a48a8.png
- seq=148 vision_frame env_step=12 sha256=b67b402094a9 path=experiment-runs\20260801T022435.912080Z\workspace-harness-0\vision_frames\env-0012-0586bff00576.png
- seq=167 vision_frame env_step=14 sha256=e73256f96a1a path=experiment-runs\20260801T022435.912080Z\workspace-harness-0\vision_frames\env-0014-f9e1faadb0e6.png
- seq=183 vision_frame env_step=15 sha256=8525d1c81c81 path=experiment-runs\20260801T022435.912080Z\workspace-harness-0\vision_frames\env-0015-b851e193da7e.png
- seq=200 vision_frame env_step=16 sha256=e6b9d15f9e79 path=experiment-runs\20260801T022435.912080Z\workspace-harness-0\vision_frames\env-0016-07ceffc18848.png

## Hypotheses and WM revisions

- seq=7 wm_revision v2 kind=write_code path=experiment-runs\20260801T022435.912080Z\workspace-harness-0\wm_versions\v0002.py
- seq=8 notes_revision v1 env_step=0 preview='# Working notes\n\n## Grounded frame objects\n\n- The 64x64 frame has a large upper '
- seq=9 hypothesis_revision v1 updated=['H_directional_control', 'H_panel_transform', 'H_identity_baseline'] experiment_id=None
- … 21 omitted …
- seq=171 notes_revision v9 env_step=14 preview='# Working notes\n\n## Grounded objects\n\n- The controlled object is a 5x5 token com'
- seq=172 hypothesis_revision v10 updated=['H_marker_goal', 'H_marker_solid'] experiment_id=None
- seq=187 wm_revision v9 kind=write_code path=experiment-runs\20260801T022435.912080Z\workspace-harness-0\wm_versions\v0009.py
- seq=188 notes_revision v10 env_step=15 preview='# Working notes\n\n## Grounded objects\n\n- The controlled object is a 5x5 token com'
- seq=189 hypothesis_revision v11 updated=['H_marker_goal', 'H_marker_solid', 'H_panel_transform', 'H_action_cost', 'H_submit_portal', 'H_marker_restores', 'H_marker_consumed'] experiment_id=None

## Backtests and BFS plans

- seq=87 bfs_plan plan_id=365a97883dfcd6e8fcc6 wm=v5 actions=1

## Prequential predictions

- seq=30 prequential_prediction kind=exploration action_id=2 events=[]
- seq=47 prequential_prediction kind=navigation action_id=1 events=[]
- seq=49 prediction_matched kind=navigation action_id=1 events=[]
- … 18 omitted …
- seq=163 prequential_prediction kind=navigation action_id=2 events=[]
- seq=165 prediction_matched kind=navigation action_id=2 events=[]
- seq=179 prequential_prediction kind=exploration action_id=3 events=[]
- seq=195 prequential_prediction kind=exploration action_id=4 events=[]
- seq=197 prediction_matched kind=exploration action_id=4 events=[]

## Commits and experiments

- (none)

## Resets, mismatches, and spend stops

- seq=32 prediction_mismatch reason=prequential prediction differs from real observation action_id=2
- seq=76 prediction_mismatch reason=prequential prediction differs from real observation action_id=1
- seq=94 prediction_mismatch reason=prequential prediction differs from real observation action_id=1
- seq=181 prediction_mismatch reason=prequential prediction differs from real observation action_id=3

## Returned reasoning text

- (none)

## How to spot-check

1. Open `hypotheses.json` and `hypothesis_versions/` for stable theory status/evidence.
2. Open `notes.md` and `notes_history/` for the readable synthesis.
3. Diff `wm_versions/vNNNN.py` around a `wm_revision` seq above.
4. In the jsonl, search `"event":"deliberation_turn"` or `"event":"model_response"`.
5. If `reasoning_status` is `tokens_only`, the channel billed reasoning tokens but returned no text.
