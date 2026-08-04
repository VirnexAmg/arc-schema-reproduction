# Working notes

## Grounded state
- The frame is a 1x3 strip. Initially it was `[0,0,0]`; action 1 produced `[1,0,0]` without level progress.
- The PNG/RLE ground color 1 at the leftmost cell and color 0 in the remaining two cells.
- Legal actions remain IDs 1 and 2. Action 2 is untried.

## Hypotheses
- `H_row_fill`: action 1 fills the first zero cell in row-major order. A strip containing only color 1 is the candidate completion state.
- `H_cursor_shift`: the new color-1 cell may instead be a cursor that will move right on another action 1, yielding `[0,1,0]`.
- `H_fixed_slot`: action 1 may control only the first cell, so repeating it could leave `[1,0,0]` unchanged or toggle it off; action 2 may control another slot.

`H_visible_noop` is rejected by transition 1 because action 1 visibly changed the leftmost cell.

## Experiments
- Transition 1: action 1 changed `[0,0,0]` to `[1,0,0]`; no progress event.
- Repeat action 1 next. `[1,1,0]` supports `H_row_fill`; `[0,1,0]` supports `H_cursor_shift`; unchanged or `[0,0,0]` supports `H_fixed_slot`.
- If row filling is confirmed, one further action 1 should produce `[1,1,1]` and plausibly win. A monitored plan should stop immediately on any mismatch.
