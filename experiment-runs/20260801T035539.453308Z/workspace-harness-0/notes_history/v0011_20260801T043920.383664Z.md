# Working notes

## Grounded objects
- The controllable object is the 5x5 color-12/9 payload. Ordinary translations preserve its visible two-row color-12 cap and three-row color-9 body.
- ACTION1, ACTION2, ACTION3, and ACTION4 map to up, down, left, and right respectively, each by five pixels when traversable.
- The asymmetric blue/black glyph in the left room is a traversable horizontal-reflection station.
- Entering the station moved the payload from row 25 to row 30, horizontally reflected the bottom-left status glyph, and did not consume a color-11 meter cell.
- Leaving the station to the right restored its exact blue/black terrain, preserved the reflected status, and resumed ordinary meter consumption.
- The reflected bottom status `111/001/101` exactly matches the 3x3 color-9 pattern in the framed upper target.
- The payload is currently at top row 30, column 24, immediately right of the station. The meter has 30 color-11 cells remaining.

## Stable hypotheses
- H_four_direction_control is supported: ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right.
- H_underlay_restore is supported for ordinary terrain and the blue/black station.
- H_glyph_transform is supported: station entry horizontally reflects the bottom status glyph, leaves the visible payload unchanged, and does not advance the meter.
- H_status_target_match remains the leading goal mechanism: return the configured payload to the upper socket after making the bottom status match the framed target.

## Evidence
- Transitions 1-6: ACTION1 moved upward from row 45 to the unmatched upper socket at row 15.
- Transition 7: further upward motion at row 15 was blocked.
- Transitions 8-9: ACTION2 undocked the payload to rows 20 and 25.
- Transitions 10-12: ACTION3 moved left from column 34 to column 19.
- Transition 13: ACTION2 entered the blue/black station, reflected the bottom status, and consumed no meter cell.
- Transition 14: ACTION4 moved right from column 19 to column 24, restored the station glyph exactly, preserved the reflected status, and consumed one meter cell. This supports H_action4_right and rejects H_action4_nonright.

## Return route
- From `(30,24)`, ACTION1 reaches the open row-25 corridor.
- Two ACTION4 steps move through columns 29 and 34, aligning with the vertical shaft.
- Two ACTION1 steps move through row 20 and into the upper socket at row 15.
- The model predicts LEVEL_COMPLETE on the final step because the reflected status matches the upper target. Any earlier mismatch should stop the monitored burst.
