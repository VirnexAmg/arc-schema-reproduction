# Trace index (auto-generated)

- agent: `harness`
- status: `model_call_budget`
- levels_completed: 0
- environment_actions: 19
- journal: `experiment-runs\20260801T035539.453308Z\harness-run-0.jsonl`
- workspace: `experiment-runs\20260801T035539.453308Z\workspace-harness-0`
- native Codex events: `experiment-runs\20260801T035539.453308Z\workspace-harness-0\codex-cli-events.jsonl` (when ARC_AGENT_RUNTIME=codex_cli)
- notes.md: `experiment-runs\20260801T035539.453308Z\workspace-harness-0\notes.md` (notes_version=11)
- hypotheses.json: `experiment-runs\20260801T035539.453308Z\workspace-harness-0\hypotheses.json` (hypothesis_version=11)
- world_model.py: `experiment-runs\20260801T035539.453308Z\workspace-harness-0\world_model.py` (wm_version=10)
- wm_versions/: `experiment-runs\20260801T035539.453308Z\workspace-harness-0\wm_versions`
- notes_history/: `experiment-runs\20260801T035539.453308Z\workspace-harness-0\notes_history`
- hypothesis_versions/: `experiment-runs\20260801T035539.453308Z\workspace-harness-0\hypothesis_versions`
- vision_frames/: `experiment-runs\20260801T035539.453308Z\workspace-harness-0\vision_frames`
- notes_revision events: 11
- wm_revision events: 9
- reasoning_status present/tokens_only: 0/12
- level_resource_checkpoints: []
- BFS plans / BFS-derived planned actions: 1/5
- navigation actions: 6
- BFS no-plan results/cache hits: 7/2
- prequential predictions/matches/mismatches: 18/11/7
- prequential approximate matches: 0
- discriminating experiments: 0
- experiments observed/resolved: 0/0
- event-driven deliberations: 11
- max deliberation context chars: 23001
- Codex transport reconnects / HTTPS fallbacks / timeouts / turn failures: 48/12/0/0
- Codex recovered post-completion process hangs: 0
- model budget exhausted at action: 19

## Level progress and boundaries

- seq=3 vision_frame env_step=0 sha256=c4c421ed71ec path=experiment-runs\20260801T035539.453308Z\workspace-harness-0\vision_frames\env-0000-aa5162a89ba4.png
- seq=17 vision_frame env_step=1 sha256=c092df09caff path=experiment-runs\20260801T035539.453308Z\workspace-harness-0\vision_frames\env-0001-35e6d552a3e8.png
- seq=43 vision_frame env_step=5 sha256=417bd9f4f0bb path=experiment-runs\20260801T035539.453308Z\workspace-harness-0\vision_frames\env-0005-29e1e0124a8a.png
- … 3 omitted …
- seq=116 vision_frame env_step=9 sha256=8291cad2435c path=experiment-runs\20260801T035539.453308Z\workspace-harness-0\vision_frames\env-0009-6e2e50e4e5da.png
- seq=133 vision_frame env_step=10 sha256=53451512a0c5 path=experiment-runs\20260801T035539.453308Z\workspace-harness-0\vision_frames\env-0010-5a731ddeb304.png
- seq=153 vision_frame env_step=12 sha256=1f6815775916 path=experiment-runs\20260801T035539.453308Z\workspace-harness-0\vision_frames\env-0012-896acbc31f2e.png
- seq=169 vision_frame env_step=13 sha256=917de2d3fd53 path=experiment-runs\20260801T035539.453308Z\workspace-harness-0\vision_frames\env-0013-0f9f116aa12e.png
- seq=186 vision_frame env_step=14 sha256=17b0cf1ff36d path=experiment-runs\20260801T035539.453308Z\workspace-harness-0\vision_frames\env-0014-b33a67228767.png

## Hypotheses and WM revisions

- seq=7 wm_revision v2 kind=apply_patch path=experiment-runs\20260801T035539.453308Z\workspace-harness-0\wm_versions\v0002.py
- seq=8 notes_revision v1 env_step=0 preview='# Working notes\n\n## Grounded entry-frame objects\n- A compact asymmetric blue/bla'
- seq=9 hypothesis_revision v1 updated=['H_directional_move', 'H_orientation_control'] experiment_id=None
- … 23 omitted …
- seq=174 notes_revision v10 env_step=13 preview='# Working notes\n\n## Grounded objects\n- The controllable object is the 5x5 color-'
- seq=175 hypothesis_revision v10 updated=['H_glyph_block', 'H_glyph_traverse', 'H_glyph_transform', 'H_status_target_match', 'H_action4_right', 'H_action4_nonright'] experiment_id=None
- seq=190 wm_revision v10 kind=apply_patch path=experiment-runs\20260801T035539.453308Z\workspace-harness-0\wm_versions\v0010.py
- seq=191 notes_revision v11 env_step=14 preview='# Working notes\n\n## Grounded objects\n- The controllable object is the 5x5 color-'
- seq=192 hypothesis_revision v11 updated=['H_action4_right', 'H_action4_nonright', 'H_four_direction_control', 'H_glyph_transform', 'H_status_target_match'] experiment_id=None

## Backtests and BFS plans

- seq=194 bfs_plan plan_id=c10a104bb77dd4f75b67 wm=v10 actions=5

## Prequential predictions

- seq=30 prequential_prediction kind=navigation action_id=1 events=[]
- seq=32 prediction_matched kind=navigation action_id=1 events=[]
- seq=33 prequential_prediction kind=navigation action_id=1 events=[]
- … 21 omitted …
- seq=205 prequential_prediction kind=planned action_id=4 events=[]
- seq=207 prediction_matched kind=planned action_id=4 events=[]
- seq=208 prequential_prediction kind=planned action_id=1 events=[]
- seq=210 prediction_matched kind=planned action_id=1 events=[]
- seq=211 prequential_prediction kind=planned action_id=1 events=['LEVEL_COMPLETE']

## Commits and experiments

- (none)

## Resets, mismatches, and spend stops

- seq=58 prediction_mismatch reason=prequential prediction differs from real observation action_id=1
- seq=75 prediction_mismatch reason=prequential prediction differs from real observation action_id=1
- seq=93 prediction_mismatch reason=prequential prediction differs from real observation action_id=2
- seq=130 prediction_mismatch reason=prequential prediction differs from real observation action_id=3
- seq=167 prediction_mismatch reason=prequential prediction differs from real observation action_id=2
- seq=184 prediction_mismatch reason=prequential prediction differs from real observation action_id=4
- seq=213 prediction_mismatch reason=prequential prediction differs from real observation action_id=1
- seq=214 model_call_budget calls=12 env_step=19

## Returned reasoning text

- (none)

## How to spot-check

1. Open `hypotheses.json` and `hypothesis_versions/` for stable theory status/evidence.
2. Open `notes.md` and `notes_history/` for the readable synthesis.
3. Diff `wm_versions/vNNNN.py` around a `wm_revision` seq above.
4. In the jsonl, search `"event":"deliberation_turn"` or `"event":"model_response"`.
5. If `reasoning_status` is `tokens_only`, the channel billed reasoning tokens but returned no text.
