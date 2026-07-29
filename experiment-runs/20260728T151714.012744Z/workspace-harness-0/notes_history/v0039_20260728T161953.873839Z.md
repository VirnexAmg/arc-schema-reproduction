# Working notes

## Grounded objects and controls
- 64x64 maze on 5x5 logical tiles.
- Recorded controls: ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right.
- Player is a 5-wide color-12 cap over a color-9 body; color 3 is route floor.
- Bottom color-11 strip is an action meter; level 2 spends two columns per ordinary input.

## Current state
- Level 2, player is now on the restored upper patterned dock at x=14,y=15.
- Entering it refilled the meter to 42 columns and changed the three warning bands to upper=full, middle=right, lower=split.
- Four reserve pixels remain at bottom-right.

## Mechanism hypotheses
- The two patterned docks form alternating recharge/status stations; visiting the currently armed dock advances the warning display and restores movement charge.
- The lower-right 0/1 floor switch modifies warning/reserve state and can force exhaustion while the upper dock is armed.
- A likely progression cycle is upper dock -> lower dock -> switch/other activation, rather than merely reaching either dock once.
- Empty charge resolves on the following input, with fatal versus checkpoint recovery determined by warning/reserve phase.

## Confirmed / ruled out
- ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right.
- Blocked inputs usually consume charge, except protected final-unit and special-dock interactions.
- The upper dock is traversable and recharges on entry in the late warning phase.
- Empty-meter recovery is phase-dependent, not always GAME_OVER.
- Reusable 0/1 glyphs are switches/triggers rather than ordinary walls.

## Next plan/test
- Travel from upper dock to lower patterned dock at x=39,y=50 using the open east-side corridor. The route is up to y=10, right to x=49, down to y=50, then left twice. This costs 17 inputs (34 meter columns), leaving enough charge.
- Observe whether lower-dock entry advances the warning cycle and refills charge as predicted.