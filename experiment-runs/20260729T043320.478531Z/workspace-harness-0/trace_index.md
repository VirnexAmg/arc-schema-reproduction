# Trace index (auto-generated)

- agent: `harness`
- status: `action_budget_exhausted`
- levels_completed: 0
- environment_actions: 220
- journal: `experiment-runs\20260729T043320.478531Z\harness-run-0.jsonl`
- workspace: `experiment-runs\20260729T043320.478531Z\workspace-harness-0`
- notes.md: `experiment-runs\20260729T043320.478531Z\workspace-harness-0\notes.md` (notes_version=32)
- world_model.py: `experiment-runs\20260729T043320.478531Z\workspace-harness-0\world_model.py` (wm_version=94)
- wm_versions/: `experiment-runs\20260729T043320.478531Z\workspace-harness-0\wm_versions`
- notes_history/: `experiment-runs\20260729T043320.478531Z\workspace-harness-0\notes_history`
- vision_frames/: `experiment-runs\20260729T043320.478531Z\workspace-harness-0\vision_frames`
- notes_revision events: 32
- wm_revision events: 93
- reasoning_status present/tokens_only: 0/381
- BFS plans / BFS-derived planned actions: 2/11
- prequential predictions/matches/mismatches: 207/183/24
- discriminating experiments: 104

## Level progress and boundaries

- seq=18 vision_frame env_step=8 sha256=658dfffb5f54 path=experiment-runs\20260729T043320.478531Z\workspace-harness-0\vision_frames\env-0008-3d6f9dccf384.png
- seq=66 vision_frame env_step=15 sha256=7f03542ae32a path=experiment-runs\20260729T043320.478531Z\workspace-harness-0\vision_frames\env-0015-1ac3de08b9d3.png
- seq=123 vision_frame env_step=16 sha256=f5e9dbf2acf9 path=experiment-runs\20260729T043320.478531Z\workspace-harness-0\vision_frames\env-0016-2769cfd07896.png
- … 160 omitted …
- seq=3540 vision_frame env_step=211 sha256=6cc08b36f41c path=experiment-runs\20260729T043320.478531Z\workspace-harness-0\vision_frames\env-0211-58450794111d.png
- seq=3547 vision_frame env_step=212 sha256=eb046de68148 path=experiment-runs\20260729T043320.478531Z\workspace-harness-0\vision_frames\env-0212-fc9d8324bde9.png
- seq=3567 vision_frame env_step=216 sha256=151f115e37c7 path=experiment-runs\20260729T043320.478531Z\workspace-harness-0\vision_frames\env-0216-d6c5f8b844f3.png
- seq=3574 vision_frame env_step=217 sha256=379aae8c106a path=experiment-runs\20260729T043320.478531Z\workspace-harness-0\vision_frames\env-0217-95c3e21b2323.png
- seq=3581 vision_frame env_step=218 sha256=90a5c78b869d path=experiment-runs\20260729T043320.478531Z\workspace-harness-0\vision_frames\env-0218-3a51573b3b6a.png

## Hypotheses and WM revisions

- seq=22 notes_revision v1 env_step=8 preview='# Working notes\n\n## Grounded objects\n- 64x64 board with yellow (4) background an'
- seq=27 wm_revision v2 kind=write_code path=experiment-runs\20260729T043320.478531Z\workspace-harness-0\wm_versions\v0002.py
- seq=70 wm_revision v3 kind=apply_patch path=experiment-runs\20260729T043320.478531Z\workspace-harness-0\wm_versions\v0003.py
- … 117 omitted …
- seq=2933 wm_revision v90 kind=apply_patch path=experiment-runs\20260729T043320.478531Z\workspace-harness-0\wm_versions\v0090.py
- seq=2942 wm_revision v91 kind=apply_patch path=experiment-runs\20260729T043320.478531Z\workspace-harness-0\wm_versions\v0091.py
- seq=2951 wm_revision v92 kind=apply_patch path=experiment-runs\20260729T043320.478531Z\workspace-harness-0\wm_versions\v0092.py
- seq=2956 wm_revision v93 kind=apply_patch path=experiment-runs\20260729T043320.478531Z\workspace-harness-0\wm_versions\v0093.py
- seq=2965 wm_revision v94 kind=apply_patch path=experiment-runs\20260729T043320.478531Z\workspace-harness-0\wm_versions\v0094.py

## Backtests and BFS plans

- seq=32 backtest passed=True checked=8 mismatch=None
- seq=36 bfs_plan plan_id=c422e147b13956fcfbd8 wm=v2 actions=7
- seq=75 backtest passed=False checked=15 mismatch=14
- … 107 omitted …
- seq=3094 bfs_no_plan error=None
- seq=3113 bfs_no_plan error=None
- seq=3133 bfs_no_plan error=None
- seq=3153 bfs_no_plan error=None
- seq=3173 bfs_no_plan error=None

## Prequential predictions

- seq=45 prequential_prediction kind=planned action_id=1 events=[]
- seq=47 prediction_matched kind=planned action_id=1 events=[]
- seq=48 prequential_prediction kind=planned action_id=1 events=[]
- … 382 omitted …
- seq=3580 prediction_matched kind=exploration action_id=1 events=[]
- seq=3585 prequential_prediction kind=exploration action_id=2 events=[]
- seq=3587 prediction_matched kind=exploration action_id=2 events=[]
- seq=3590 prequential_prediction kind=exploration action_id=3 events=[]
- seq=3592 prediction_matched kind=exploration action_id=3 events=[]

## Commits and experiments

- seq=41 commit kind=planned plan_id=c422e147b13956fcfbd8 experiment_id=None accepted=7
- seq=111 experiment id=exp-93240296444a9166 action_id=2 hypotheses=2
- seq=116 commit kind=exploration plan_id=None experiment_id=exp-93240296444a9166 accepted=1
- … 244 omitted …
- seq=3157 experiment id=exp-3c5f20252b62e51c action_id=1 hypotheses=2
- seq=3162 commit kind=exploration plan_id=None experiment_id=exp-3c5f20252b62e51c accepted=1
- seq=3177 commit kind=exploration plan_id=None experiment_id=None accepted=None
- seq=3181 experiment id=exp-7b1c749d763cf40d action_id=3 hypotheses=2
- seq=3186 commit kind=exploration plan_id=None experiment_id=exp-7b1c749d763cf40d accepted=1

## Resets, mismatches, and spend stops

- seq=65 prediction_mismatch reason=prequential prediction differs from real observation action_id=1
- seq=160 prediction_mismatch reason=prequential prediction differs from real observation action_id=2
- seq=217 prediction_mismatch reason=prequential prediction differs from real observation action_id=2
- … 17 omitted …
- seq=2167 prediction_mismatch reason=prequential prediction differs from real observation action_id=3
- seq=2247 prediction_mismatch reason=prequential prediction differs from real observation action_id=2
- seq=2842 prediction_mismatch reason=prequential prediction differs from real observation action_id=2
- seq=2922 prediction_mismatch reason=prequential prediction differs from real observation action_id=4
- seq=2923 life_reset #1 levels=0

## Returned reasoning text

- (none)

## How to spot-check

1. Open `notes.md` and `notes_history/` for hypothesis text.
2. Diff `wm_versions/vNNNN.py` around a `wm_revision` seq above.
3. In the jsonl, search `"event":"deliberation_turn"` or `"event":"model_response"`.
4. If `reasoning_status` is `tokens_only`, the channel billed reasoning tokens but returned no text.
