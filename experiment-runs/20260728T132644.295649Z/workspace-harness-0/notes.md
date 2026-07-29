# Working notes

## Grounded objects
- Main playfield is a 5-pixel lattice maze (3=floor, 4=wall); token is a 5x5 object with two color-12 rows above three color-9 rows.
- Rows 61-62 contain the 42-column attempt strip and three status lamps.
- Level 2 has a framed target at x12..20,y38..46 encoding 111/100/101, a reusable raw 0/1 operator centered near x47..51,y46..48, and two consumable raw 11 refill glyphs.
- Current token top-left is (44,45), overlapping the raw 0/1 operator. Current register is 101/001/111; target is 111/100/101. The attempt strip has 14 columns remaining (7 ordinary level-2 actions).

## Established mechanisms
- ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right.
- Legal movement shifts one 5-pixel lattice cell; ordinary actions spend meter, with level 2 spending two columns.
- Entering a raw 11 glyph refills all 42 attempt columns, spends no step, leaves the register unchanged, and consumes the glyph.
- Attempt-strip exhaustion triggers checkpoint reset on the following action.
- Level 1's raw 0/1 glyph transformed the register; submitting the matching register at its framed terminal completed the level.
- Level 2's framed target blocks direct downward traversal from (14,35).
- Repeatedly leaving the level-2 0/1 glyph downward and re-entering upward at the current phase leaves register 101/001/111 unchanged while spending meter.
- The current right-hand operator branch is locally isolated from the main maze; exhaustion/reset is the practical return route to the upper checkpoint.

## Mechanism hypotheses
- H1: Level 2's raw 0/1 glyph transform is phase- and/or incoming-register-dependent rather than a simple transformation on every entry.
- H2: The framed pattern is the required register target 111/100/101 and submission terminal, analogous to level 1.
- H3: Raw 11 glyphs are consumable refill/checkpoint operators; consuming the upper one established the exhaustion respawn at (29,40).
- H4: Framing distinguishes target/submission roles while raw embedded glyphs identify operators.

## Ruled out
- Raw 11 glyphs are decorative or reusable.
- Level-2 meter rate depends on a lower 11 glyph remaining visible.
- The framed 9-pattern is directly passable from above.
- Level coordinates/routes remain fixed after level-up.
- Every entry into the level-2 0/1 glyph necessarily changes the register.

## Next plan
- Exhaust the remaining 14 strip columns with blocked ACTION3 attempts, then issue one additional action to trigger checkpoint reset and resume at (29,40). Route from there toward the framed terminal or remaining refill glyph.