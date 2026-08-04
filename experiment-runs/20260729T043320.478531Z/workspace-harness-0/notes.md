# Working notes

## Grounded objects
- Yellow (4) is wall/background; green (3) and gray (5) form traversable corridors/chambers.
- Avatar is a 5x5 block with two color-12 rows over three color-9 rows; after life reset it respawns at (30,45).
- Small blue/black glyph near (16..18,31..33) is a directional switch; upper red 3x3 glyph is a lock/target.
- Bottom-left 10x6 panel is a doubled-pixel 3x3 FSM display. The cyan strip at rows 61..62 is the ordinary-input budget.

## Established dynamics
- ACTION1 up, ACTION2 down, ACTION3 left, ACTION4 right; successful movement is in 5-cell increments.
- Switch contacts update the display. Ordinary moves/collisions generally spend one cyan column; some recognized interactions and lock attempts are free.
- Exhausting the cyan meter and then acting causes GAME_OVER; the harness life reset restores the entry frame and full meter.
- The pre-death ACTION4 moved right from (15,25) to (20,25), consumed the last remaining cyan tick, and produced GAME_OVER. Thus reaching zero budget is itself terminal on that action, rather than waiting for a subsequent timeout-reset input.
- Life reset restores avatar, HUD, collectible/checkpoint, and budget to the original entry projection; latent phase persistence across a life boundary is not yet established.

## Current hypotheses
- Current HUD is `### / #.. / #.#`; upper lock is `### / ..# / #.#`.
- H_direct: direct top-to-bottom display equality is required; directional switch contacts transform display rows.
- H_sequence: the lock checks a directional sequence encoded by its pixels rather than static equality alone.

## Falsified
- Immediate lock adjacency completes without matching: false.
- Reflected/bottom-to-top equality unlocks: false.
- Meter advances iff movement succeeds: false.
- Three right contacts alone unlocks: false.
- Timeout clears and respawns within the same life after the budget reaches zero: false for the latest episode; depletion instead produced GAME_OVER immediately.
- Every late left contact has the same effect: false.
- The prior model's gated row-30 reversal rule was false: downward switch contact itself selects middle-left, even without an immediately preceding ACTION1.

## Needs testing
- Re-certify the full transition model after life reset.
- Determine which approach direction transforms the outer display rows toward `### / ..# / #.#` while conserving enough budget to revisit the lock.
- Test the upper lock once direct equality is obtained.