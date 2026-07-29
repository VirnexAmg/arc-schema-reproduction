# Working notes

## Objects
- Movable 5x5 token: 2x5 color-12 cap over 3x5 color-9 body.
- Color 3 corridor and color 5 room floor are traversable; color 4 is wall.
- The 0/1 glyph is a traversable control, hidden while covered and restored on departure.
- Upper patterned chamber is a receptacle/goal region.
- Lower-left 9/5 motif is a control/status display.
- Two-row color-11 strip is a movement budget; spent columns become color 3.

## Established mechanisms
- ACTION1=up, ACTION2=down, ACTION3=left from direct transitions; ACTION4 inferred right.
- Successful token motion occurs in 5-pixel increments.
- Ordinary recent ACTION2 corridor moves each consumed one budget column.

## Current mismatch and falsified hypotheses
- Replay mismatch remains at checked transition 7, ACTION2: model consumes one extra meter column while geometry and other displays agree.
- Blanket downward-free is falsified by consecutive recent ACTION2 moves, each visibly consuming a column.
- Blanket all-actions-spend also fails transition 7.
- The tested status-only refund predicate did not resolve replay, so the status motif alone is insufficient or the exceptional event is goal/receptacle completion.
- Coordinate threshold plus status refund also failed; simple source-y classification is inadequate.

## Current hypotheses
- H1: completing/occupying the upper receptacle refunds or does not consume a movement column; this should be grounded by the completed upper token silhouette, not one memorized cell.
- H2: a hidden one-shot control credit is carried through the state and consumed at transition 7; visible status pixels do not fully represent it.
- H3: budget consumption is delayed/coupled to a distinct event rather than every action.

## Next testing
- Current token is at y=35. A lateral action can test corridor layout/action mapping while avoiding further unproductive meter-rule rewrites. Re-run full backtest after the latest receptacle-completion patch before any planned search.