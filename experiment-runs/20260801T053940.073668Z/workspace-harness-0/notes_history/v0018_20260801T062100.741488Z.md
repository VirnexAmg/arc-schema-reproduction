# Working notes

## Confirmed transformation

- Two final switch entries rotated the doubled bottom glyph into 111/100/101, an exact 2x match for the framed reference.
- The matched panel remained unchanged throughout the route to the upper recharge ring.
- The persistent switch is visible again after being vacated.

## Confirmed resource route

- Seven ACTION1 moves reached row 10 and seven ACTION3 moves crossed to column 14 exactly as predicted.
- The bar reached four cells per row immediately before the remaining ring.
- ACTION2 entered the upper compact color-11 ring and restored both bar rows to their full 42-cell span.
- The controlled tile now occupies rows 15-19, columns 14-18 and covers that ring.
- Both level-2 rings are now consumed or covered, so visible color 11 can no longer be the sole cue for the persistent two-cell movement rate. The doubled 6x6 glyph also identifies this layout in the model.

## Immediate completion route

- Five ACTION2 moves descend the open column-14 corridor through rows 20, 25, 30, and 35, then enter the matched framed color-9 endpoint at rows 40-44.
- The first four moves should consume two cells per bar row, leaving 34 before endpoint entry.
- The fifth move should emit LEVEL_COMPLETE and expose the unseen next-level entry grid.

## Revision triggers

- Revise the level-rate representation if the first move after covering the last ring consumes anything other than two cells.
- Revise H_glyph_match_unlock if the fifth downward move is blocked or does not cause a level boundary.
