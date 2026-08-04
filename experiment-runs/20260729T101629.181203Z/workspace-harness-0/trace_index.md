# Trace index (auto-generated)

- agent: `harness`
- status: `spend_budget`
- levels_completed: 1
- environment_actions: 176
- journal: `experiment-runs\20260729T101629.181203Z\harness-run-0.jsonl`
- workspace: `experiment-runs\20260729T101629.181203Z\workspace-harness-0`
- notes.md: `experiment-runs\20260729T101629.181203Z\workspace-harness-0\notes.md` (notes_version=12)
- hypotheses.json: `experiment-runs\20260729T101629.181203Z\workspace-harness-0\hypotheses.json` (hypothesis_version=81)
- world_model.py: `experiment-runs\20260729T101629.181203Z\workspace-harness-0\world_model.py` (wm_version=33)
- wm_versions/: `experiment-runs\20260729T101629.181203Z\workspace-harness-0\wm_versions`
- notes_history/: `experiment-runs\20260729T101629.181203Z\workspace-harness-0\notes_history`
- hypothesis_versions/: `experiment-runs\20260729T101629.181203Z\workspace-harness-0\hypothesis_versions`
- vision_frames/: `experiment-runs\20260729T101629.181203Z\workspace-harness-0\vision_frames`
- notes_revision events: 12
- wm_revision events: 32
- reasoning_status present/tokens_only: 0/431
- BFS plans / BFS-derived planned actions: 0/0
- prequential predictions/matches/mismatches: 162/156/6
- prequential approximate matches: 36
- discriminating experiments: 20
- experiments observed/resolved: 18/16
- event-driven deliberations: 160
- model budget exhausted at action: None

## Level progress and boundaries

- seq=19 vision_frame env_step=8 sha256=658dfffb5f54 path=experiment-runs\20260729T101629.181203Z\workspace-harness-0\vision_frames\env-0008-3d6f9dccf384.png
- seq=49 vision_frame env_step=9 sha256=c2ccecd6e1ee path=experiment-runs\20260729T101629.181203Z\workspace-harness-0\vision_frames\env-0009-0cf7e3df4720.png
- seq=70 vision_frame env_step=10 sha256=57e86742bb52 path=experiment-runs\20260729T101629.181203Z\workspace-harness-0\vision_frames\env-0010-c1064f9bcedf.png
- … 154 omitted …
- seq=3193 vision_frame env_step=172 sha256=94aa380e39fc path=experiment-runs\20260729T101629.181203Z\workspace-harness-0\vision_frames\env-0172-eaf49535c5f3.png
- seq=3214 vision_frame env_step=173 sha256=d68470cf3168 path=experiment-runs\20260729T101629.181203Z\workspace-harness-0\vision_frames\env-0173-365c8577db5b.png
- seq=3230 vision_frame env_step=174 sha256=28490094c74b path=experiment-runs\20260729T101629.181203Z\workspace-harness-0\vision_frames\env-0174-4dc639211085.png
- seq=3246 vision_frame env_step=175 sha256=c6b460527e9f path=experiment-runs\20260729T101629.181203Z\workspace-harness-0\vision_frames\env-0175-9371110be905.png
- seq=3262 vision_frame env_step=176 sha256=2c5eec8395ee path=experiment-runs\20260729T101629.181203Z\workspace-harness-0\vision_frames\env-0176-83558d4fd645.png

## Hypotheses and WM revisions

- seq=23 wm_revision v2 kind=write_code path=experiment-runs\20260729T101629.181203Z\workspace-harness-0\wm_versions\v0002.py
- seq=32 hypothesis_revision v1 updated=['H_navigation', 'H_target'] experiment_id=None
- seq=53 notes_revision v1 env_step=9 preview='# Working notes\n\n## Grounded objects\n- The movable 5x5 magenta/dark-red marker i'
- … 97 omitted …
- seq=3105 hypothesis_revision v78 updated=['H_level2_navigation', 'H_multi_transform', 'H_timeout_reset'] experiment_id=None
- seq=3130 hypothesis_revision v79 updated=['H_level2_navigation', 'H_multi_transform', 'H_timeout_reset'] experiment_id=None
- seq=3159 hypothesis_revision v80 updated=['H_level2_navigation', 'H_multi_transform', 'H_timeout_reset'] experiment_id=None
- seq=3176 hypothesis_revision v81 updated=['H_timeout_reset', 'H_level2_navigation', 'H_multi_transform'] experiment_id=None
- seq=3197 notes_revision v12 env_step=172 preview='# Working notes\n\n## Level 1 confirmed mechanism\n- Actions map to 1 up, 2 down, 3'

## Backtests and BFS plans

- seq=28 backtest passed=True checked=8 mismatch=None
- seq=143 backtest passed=True checked=14 mismatch=None
- seq=181 backtest passed=True checked=15 mismatch=None
- … 79 omitted …
- seq=2665 bfs_no_plan error=None
- seq=2764 backtest passed=True checked=149 mismatch=None
- seq=2768 bfs_no_plan error=None
- seq=2880 bfs_no_plan error=None
- seq=3010 bfs_no_plan error=None

## Prequential predictions

- seq=45 prequential_prediction kind=exploration action_id=1 events=[]
- seq=47 prediction_matched kind=exploration action_id=1 events=[]
- seq=66 prequential_prediction kind=exploration action_id=1 events=[]
- … 309 omitted …
- seq=3228 prediction_matched kind=exploration action_id=1 events=[]
- seq=3242 prequential_prediction kind=exploration action_id=1 events=[]
- seq=3244 prediction_matched kind=exploration action_id=1 events=[]
- seq=3258 prequential_prediction kind=exploration action_id=1 events=[]
- seq=3260 prediction_matched kind=exploration action_id=1 events=[]

## Commits and experiments

- seq=37 commit kind=exploration plan_id=None experiment_id=None accepted=None
- seq=41 commit kind=exploration plan_id=None experiment_id=None accepted=1
- seq=58 commit kind=exploration plan_id=None experiment_id=None accepted=None
- … 281 omitted …
- seq=3234 commit kind=exploration plan_id=None experiment_id=None accepted=None
- seq=3238 commit kind=exploration plan_id=None experiment_id=None accepted=1
- seq=3250 commit kind=exploration plan_id=None experiment_id=None accepted=None
- seq=3254 commit kind=exploration plan_id=None experiment_id=None accepted=1
- seq=3266 commit kind=exploration plan_id=None experiment_id=None accepted=None

## Resets, mismatches, and spend stops

- seq=132 prediction_mismatch reason=prequential prediction differs from real observation action_id=1
- seq=170 prediction_mismatch reason=prequential prediction differs from real observation action_id=1
- seq=306 prediction_mismatch reason=prequential prediction differs from real observation action_id=2
- seq=796 prediction_mismatch reason=prequential prediction differs from real observation action_id=4
- seq=1973 prediction_mismatch reason=prequential prediction error: SandboxError: predict() raised NameError: name 'LEVEL_COMPLETE' is not defined action_id=1
- seq=2344 prediction_mismatch reason=prequential prediction differs from real observation action_id=2
- seq=3269 spend_budget cost=29.307372000000015 cap=30.0

## Returned reasoning text

- (none)

## How to spot-check

1. Open `hypotheses.json` and `hypothesis_versions/` for stable theory status/evidence.
2. Open `notes.md` and `notes_history/` for the readable synthesis.
3. Diff `wm_versions/vNNNN.py` around a `wm_revision` seq above.
4. In the jsonl, search `"event":"deliberation_turn"` or `"event":"model_response"`.
5. If `reasoning_status` is `tokens_only`, the channel billed reasoning tokens but returned no text.
