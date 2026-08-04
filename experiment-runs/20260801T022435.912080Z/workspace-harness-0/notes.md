# Working notes

## Grounded objects

- The controlled object is a 5x5 token composed of two color-12 rows above three color-9 rows.
- Successful ordinary movement translates the token by five pixels and consumes one color-11 meter column.
- The compact 0/1 glyph is an enterable transform switch, not a solid obstacle.
- The lower-left 5/9 panel encodes `111/100/101` initially; entering the glyph reflected its sparse middle row to produce `111/001/101`.
- The upper 5/9 panel depicts the resulting `111/001/101` target.
- Marker entry itself consumes no meter energy.
- The upper panel admits the token into a stopping pad but blocks a second upward move.

## Stable hypotheses

- H_directional_control: ACTION1 moves up, ACTION2 down, and ACTION3 left; ACTION4 is predicted to move right.
- H_action_cost: ordinary successful moves consume one meter column, blocked moves consume none, and transform-switch entry is free.
- H_panel_transform: confirmed; entering the 0/1 glyph horizontally reflects the unique sparse row-pair in the lower 5/9 panel.
- H_marker_goal is revised: the glyph is a transform switch rather than the terminal goal.
- H_marker_solid is rejected.
- H_submit_portal: after the transformed lower pattern matches the upper target, returning to the upper stopping pad is the strongest completion mechanism.
- H_marker_restores and H_marker_consumed remain alternatives for what is revealed when the token leaves the switch.
- H_underlay remains confirmed for ordinary floor and the upper panel.

## Evidence and next probe

- Direct ACTION3 contact moved the token from x=24 to x=19, overwrote the visible 0/1 glyph, did not consume a meter column, and reflected the lower panel's middle row from `100` to `001`.
- This falsified the conservative collision model and exactly matches the upper target pattern.
- The revised model treats the switch as a reversible reflection and tracks odd/even transform parity.
- ACTION4 is the next legal probe. The main prediction is a rightward move to x=24, restoration of the glyph underlay, preservation of the reflected panel, and one ordinary meter cost. If exact search is available after recertification, the useful goal route is back to the upper stopping pad.
