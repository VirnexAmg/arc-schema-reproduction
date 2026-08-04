# Working notes

## Grounded objects

- The interaction area is a maze quantized into 5-by-5 cells on color-3 floor, with color-4 gaps acting as walls.
- The 5-by-5 color-12/9 tile is the controlled token. Action 1 moved it exactly one maze cell upward, from rows 45-49 to rows 40-44, while preserving its pattern.
- The compact color-0/1 glyph near rows 31-33 did not move. It remains a strong destination or goal-marker candidate.
- The upper framed glyph did not change on action 1.
- The long color-11 HUD bar on rows 61-62 lost its leftmost column on the turn, indicating a likely per-action budget. Three color-8 marks at the right may be lives or attempts.

## Stable hypotheses

- H_avatar_motion is rejected: the 0/1 glyph stayed fixed while the 12/9 tile moved.
- H_panel_action is revised into the reusable token mechanism: actions move the separate 12/9 token by 5-cell maze steps; observed action 1 is up.
- H_goal_marker: reaching the cell containing the 0/1 glyph likely completes the level or triggers an interaction.
- H_step_meter: every submitted action removes one column from the color-11 budget bar.
- Effects of actions 2-4 are still unknown and remain identity in the executable model until observed.

## Experiments

- Transition 1 ruled out central-glyph control and panel-only manipulation. It established action 1 = one cell up and exposed the action-budget redraw.
- Next probe action 2. A 5-cell token displacement will identify another direction; a HUD-only change means the direction is blocked at the current token location or action 2 is contextual.
