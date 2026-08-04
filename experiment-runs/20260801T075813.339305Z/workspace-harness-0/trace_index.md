# Trace index (auto-generated)

- agent: `harness`
- status: `model_call_budget`
- levels_completed: 2
- environment_actions: 496
- journal: `experiment-runs\20260801T075813.339305Z\harness-run-0.jsonl`
- workspace: `experiment-runs\20260801T075813.339305Z\workspace-harness-0`
- native Codex events: `experiment-runs\20260801T075813.339305Z\workspace-harness-0\codex-cli-events.jsonl` (when ARC_AGENT_RUNTIME=codex_cli)
- notes.md: `experiment-runs\20260801T075813.339305Z\workspace-harness-0\notes.md` (notes_version=72)
- hypotheses.json: `experiment-runs\20260801T075813.339305Z\workspace-harness-0\hypotheses.json` (hypothesis_version=72)
- world_model.py: `experiment-runs\20260801T075813.339305Z\workspace-harness-0\world_model.py` (wm_version=54)
- wm_versions/: `experiment-runs\20260801T075813.339305Z\workspace-harness-0\wm_versions`
- notes_history/: `experiment-runs\20260801T075813.339305Z\workspace-harness-0\notes_history`
- hypothesis_versions/: `experiment-runs\20260801T075813.339305Z\workspace-harness-0\hypothesis_versions`
- vision_frames/: `experiment-runs\20260801T075813.339305Z\workspace-harness-0\vision_frames`
- notes_revision events: 72
- wm_revision events: 53
- reasoning_status present/tokens_only: 0/72
- level_resource_checkpoints: [{"cached_prompt_tokens":536576,"completion_tokens":69415,"environment_actions":19,"estimated_cost_usd":null,"level":1,"model_calls":8,"prompt_tokens":791929,"reasoning_tokens":38636,"total_tokens":861344},{"cached_prompt_tokens":4963584,"completion_tokens":634223,"environment_actions":336,"estimated_cost_usd":null,"level":2,"model_calls":50,"prompt_tokens":7477778,"reasoning_tokens":428270,"total_tokens":8112001}]
- BFS plans / BFS-derived planned actions: 3/14
- navigation actions: 461
- BFS no-plan results/cache hits: 33/9
- prequential predictions/matches/mismatches: 489/475/14
- prequential approximate matches: 27
- discriminating experiments: 0
- experiments observed/resolved: 0/0
- event-driven deliberations: 72
- max deliberation context chars: 48611
- Codex transport reconnects / HTTPS fallbacks / timeouts / turn failures: 0/0/0/0
- Codex recovered post-completion process hangs: 0
- model budget exhausted at action: 496

## Level progress and boundaries

- seq=3 vision_frame env_step=0 sha256=c4c421ed71ec path=experiment-runs\20260801T075813.339305Z\workspace-harness-0\vision_frames\env-0000-aa5162a89ba4.png
- seq=17 vision_frame env_step=1 sha256=c092df09caff path=experiment-runs\20260801T075813.339305Z\workspace-harness-0\vision_frames\env-0001-35e6d552a3e8.png
- seq=34 vision_frame env_step=2 sha256=63e3f26b02cc path=experiment-runs\20260801T075813.339305Z\workspace-harness-0\vision_frames\env-0002-a56d194d7a0e.png
- … 70 omitted …
- seq=2236 vision_frame env_step=443 sha256=2e1e07e6b9cd path=experiment-runs\20260801T075813.339305Z\workspace-harness-0\vision_frames\env-0443-21fe4d99fbcf.png
- seq=2282 vision_frame env_step=454 sha256=aa31ce18c83d path=experiment-runs\20260801T075813.339305Z\workspace-harness-0\vision_frames\env-0454-8861a17b73f9.png
- seq=2334 vision_frame env_step=467 sha256=ce27994862fe path=experiment-runs\20260801T075813.339305Z\workspace-harness-0\vision_frames\env-0467-5a09312d518e.png
- seq=2378 vision_frame env_step=477 sha256=122aec51b2cc path=experiment-runs\20260801T075813.339305Z\workspace-harness-0\vision_frames\env-0477-aa39c80b8e19.png
- seq=2439 vision_frame env_step=493 sha256=e54d715849c4 path=experiment-runs\20260801T075813.339305Z\workspace-harness-0\vision_frames\env-0493-b8de0a57e476.png

## Hypotheses and WM revisions

- seq=7 wm_revision v2 kind=apply_patch path=experiment-runs\20260801T075813.339305Z\workspace-harness-0\wm_versions\v0002.py
- seq=8 notes_revision v1 env_step=0 preview='# Working notes\n\n## Grounded objects\n- A black/blue 3x3 motif near row 31, colum'
- seq=9 hypothesis_revision v1 updated=['H_actor_motion', 'H_glyph_gate', 'H_room_navigation'] experiment_id=None
- … 189 omitted …
- seq=2383 notes_revision v71 env_step=477 preview='# Working notes\n\n## Level progress\n- Level 2 completed at evidence 336.\n- Level '
- seq=2384 hypothesis_revision v71 updated=['H_current_orientation', 'H_level3_switch', 'H_soft_reset_objects'] experiment_id=None
- seq=2443 wm_revision v54 kind=apply_patch path=experiment-runs\20260801T075813.339305Z\workspace-harness-0\wm_versions\v0054.py
- seq=2444 notes_revision v72 env_step=493 preview='# Working notes\n\n## Level progress\n- Level 2 completed at evidence 336.\n- Level '
- seq=2445 hypothesis_revision v72 updated=['H_current_orientation', 'H_level3_portal', 'H_level3_cyan_transfer', 'H_level3_switch'] experiment_id=None

## Backtests and BFS plans

- seq=128 bfs_plan plan_id=b42ed2f1dd6cfb016435 wm=v7 actions=6
- seq=160 bfs_plan plan_id=a2158835a69fc0dd9964 wm=v8 actions=1
- seq=835 bfs_plan plan_id=70ebb14abaa4db0b1a44 wm=v19 actions=7

## Prequential predictions

- seq=30 prequential_prediction kind=exploration action_id=2 events=[]
- seq=47 prequential_prediction kind=exploration action_id=3 events=[]
- seq=64 prequential_prediction kind=exploration action_id=4 events=[]
- … 956 omitted …
- seq=2451 prequential_prediction kind=navigation action_id=2 events=[]
- seq=2453 prediction_matched kind=navigation action_id=2 events=[]
- seq=2454 prequential_prediction kind=navigation action_id=2 events=[]
- seq=2456 prediction_matched kind=navigation action_id=2 events=[]
- seq=2457 prequential_prediction kind=navigation action_id=2 events=[]

## Commits and experiments

- (none)

## Resets, mismatches, and spend stops

- seq=32 prediction_mismatch reason=prequential prediction differs from real observation action_id=2
- seq=49 prediction_mismatch reason=prequential prediction differs from real observation action_id=3
- seq=118 prediction_mismatch reason=prequential prediction differs from real observation action_id=2
- … 10 omitted …
- seq=2186 prediction_mismatch reason=prequential prediction differs from real observation action_id=2
- seq=2217 life_reset #3 levels=2
- seq=2332 prediction_mismatch reason=prequential prediction differs from real observation action_id=2
- seq=2459 prediction_mismatch reason=prequential prediction differs from real observation action_id=2
- seq=2460 model_call_budget calls=72 env_step=496

## Returned reasoning text

- (none)

## How to spot-check

1. Open `hypotheses.json` and `hypothesis_versions/` for stable theory status/evidence.
2. Open `notes.md` and `notes_history/` for the readable synthesis.
3. Diff `wm_versions/vNNNN.py` around a `wm_revision` seq above.
4. In the jsonl, search `"event":"deliberation_turn"` or `"event":"model_response"`.
5. If `reasoning_status` is `tokens_only`, the channel billed reasoning tokens but returned no text.
