# Working notes

## Level progress
- Level 2 completed at evidence 336.
- Level 3 movement, portal/recharge routing, switch transforms, reset behavior, and two rejected purple target relations are grounded through evidence 493.

## Current grounded state
- Evidence 478-485 matched eight upward moves from spawn, including transport through the blue-edged portal to rows 5-9, columns 34-38.
- Evidence 486-489 matched left, down, down, right through the upper cyan source. The source was consumed for free and both timer rows refilled to 42.
- Evidence 490-493 matched down, down, down, left. The actor is now at rows 30-34, columns 29-33 with 34 timer cells per row, the initial half-turn display preserved, the lower source intact, and two reserve pairs remaining.

## Falsified goal relations
- Exact purple equality was rejected at evidence 439.
- Purple half-turn alignment was rejected at evidence 467.
- Rejected contacts leave the actor in place and do not consume timer cells.

## Active goal hypothesis
- The next executable candidate is the target's top-bottom reflection.
- The restored display is the target's half-turn. The working switch model predicts that entering the central switch from above applies a left-right reflection, whose composition with the half-turn produces the target's top-bottom reflection.
- Above entry is not yet directly observed. If its transform or the resulting target contact disagrees, revise this branch before testing the remaining left-right target relation.

## Immediate route
- From rows 30-34, columns 29-33, go down three times to enter the central switch from above, then right, up, left, up twice to return to the wide corridor.
- Go right five times and down three times to stop immediately above the exit with two timer cells remaining.
- Press down for the predicted free top-bottom target-contact completion.
