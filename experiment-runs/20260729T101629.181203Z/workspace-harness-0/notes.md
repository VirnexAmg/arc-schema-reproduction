# Working notes

## Level 1 confirmed mechanism
- Actions map to 1 up, 2 down, 3 left, 4 right; the 5x5 player moves in 5-pixel increments.
- The tiny black/blue glyph transforms the lower-left status glyph: vertical passage reflects left-right and horizontal passage reflects top-bottom.
- Matching the status to the target and pushing upward from the top socket completed level 1.

## Level 2 grounding
- Movement mapping persists. The lower-left status panel is 101/001/101; the solid patterned chamber is 111/100/101, so another transform is needed.
- The upper color-11 glyph had a conditional refill effect but did not transform status.
- Countdown exhaustion restores the exact level-entry frame on the following input.
- The lower-right cyan/black marker is near x=40,y=47, southwest of the far-right shaft, and remains the leading missing-transform candidate.

## Current state and optimized route
- Timeout restoration occurred, then ACTION1 moved the player from entry near (29,40) to (29,35). The timer has 40 dark cells, about 20 actions.
- Omit all previously tested blocked probes.
- From (29,35): east once into the central shaft; north five times to the top corridor; east three times to x≈49; south seven times to y≈45; then west once toward/crossing the lower-right marker.
- This route should fit within the timer with roughly two actions spare. Observe the marker crossing before deciding how to return to the patterned chamber.