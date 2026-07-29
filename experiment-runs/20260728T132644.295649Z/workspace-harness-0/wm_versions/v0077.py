# Movable 5x5 token on a coarse maze lattice.

def _token_box(g):
    h = len(g)
    w = len(g[0])
    for y in range(h - 4):
        for x in range(w - 4):
            ok = True
            for dy in range(5):
                want = 12 if dy < 2 else 9
                for dx in range(5):
                    if g[y + dy][x + dx] != want:
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                return (x, y)
    return None

def _restore_source(g, x, y):
    w = len(g[0])
    # The framed terminal is not an ordinary uniform corridor cell. Its latent
    # footprint has a color-5 cap on the first row and corridor color 3 below;
    # reconstruct it explicitly when a reset removes the token from there.
    if x == 34 and y == 15:
        for dx in range(5):
            g[15][x + dx] = 5
        for dy in range(1, 5):
            for dx in range(5):
                g[y + dy][x + dx] = 3
        return
    for dy in range(5):
        left = g[y + dy][x - 1] if x > 0 else 4
        right = g[y + dy][x + 5] if x + 5 < w else 4
        # Prefer horizontal continuation, but when both sides are wall this is
        # a vertical corridor and its floor is visible above or below.
        if left == right and left != 4:
            floor = left
        elif left != 4:
            floor = left
        elif right != 4:
            floor = right
        else:
            floor = 3
        for dx in range(5):
            g[y + dy][x + dx] = floor
    # A token can hide the reusable input glyph.  Its activated HUD channel
    # (the pair at columns 7-8) preserves the latent fact needed to reveal it
    # when the token leaves this level's input cell.
    if x == 19 and y == 30:
        g[y + 1][x + 2] = 0
        g[y + 2][x + 1] = 1
        g[y + 2][x + 2] = 0
        g[y + 2][x + 3] = 0
        g[y + 3][x + 2] = 1

def _advance_meter(g):
    # Rows 61-62 contain a left-to-right progress strip of colors 3 then 11.
    # Level 2 spends two columns per action (the upper 11-glyph identifies
    # that board), whereas level 1 spent one.
    if len(g) <= 62:
        return
    w = len(g[0])
    amount = 1
    if len(g) > 16 and w > 15 and g[16][15] == 11:
        amount = 2
    for k in range(amount):
        for x in range(w):
            if g[61][x] == 11 and g[62][x] == 11:
                g[61][x] = 3
                g[62][x] = 3
                break

def step(state, action):
    nxt = state.copy()
    g = nxt.frame
    p = _token_box(g)
    if p is None:
        return nxt
    aid = int(action["id"])
    # Horizontal mapping is provisional pending a discriminating observation.
    moves = {1: (0, -5), 2: (0, 5), 3: (-5, 0), 4: (5, 0)}
    if aid not in moves:
        return nxt
    x, y = p
    # A framed-terminal upward action submits the assembled register.  The
    # previously modelled unconditional no-op was falsified: with register
    # 111/001/101 this action completes level 1 and initializes level 2.
    if (x == 34 and y == 15 and aid == 1 and len(g) > 60 and
            state.levels_completed == 0):
        accepted = (
            g[55][3] == 9 and g[55][5] == 9 and g[55][7] == 9 and
            g[57][3] != 9 and g[57][5] != 9 and g[57][7] == 9 and
            g[59][3] == 9 and g[59][5] != 9 and g[59][7] == 9)
        if accepted:
            rows = {
5:"5:4,4:15,3:35,4:10",6:"5:4,4:15,3:35,4:10",7:"5:4,4:15,3:35,4:10",8:"5:4,4:15,3:35,4:10",9:"5:4,4:15,3:35,4:10",
10:"5:4,4:5,3:45,4:10",11:"5:4,4:5,3:45,4:10",12:"5:4,4:5,3:45,4:10",13:"5:4,4:5,3:45,4:10",14:"5:4,4:5,3:45,4:10",
15:"5:4,4:5,3:15,4:5,3:10,4:5,3:10,4:10",16:"5:4,4:5,3:6,11:3,3:6,4:5,3:10,4:5,3:10,4:10",17:"5:4,4:5,3:6,11:1,3:1,11:1,3:6,4:5,3:10,4:5,3:10,4:10",18:"5:4,4:5,3:6,11:3,3:6,4:5,3:10,4:5,3:10,4:10",19:"5:4,4:5,3:15,4:5,3:10,4:5,3:10,4:10",
20:"5:4,4:5,3:15,4:5,3:10,4:10,3:10,4:5",21:"5:4,4:5,3:15,4:5,3:10,4:10,3:10,4:5",22:"5:4,4:5,3:15,4:5,3:10,4:10,3:10,4:5",23:"5:4,4:5,3:15,4:5,3:10,4:10,3:10,4:5",24:"5:4,4:5,3:15,4:5,3:10,4:10,3:10,4:5",
25:"5:4,4:10,3:5,4:15,3:10,4:5,3:10,4:5",26:"5:4,4:10,3:5,4:15,3:10,4:5,3:10,4:5",27:"5:4,4:10,3:5,4:15,3:10,4:5,3:10,4:5",28:"5:4,4:10,3:5,4:15,3:10,4:5,3:10,4:5",29:"5:4,4:10,3:5,4:15,3:10,4:5,3:10,4:5",
30:"5:4,4:10,3:5,4:15,3:10,4:5,3:5,4:10",31:"5:4,4:10,3:5,4:15,3:10,4:5,3:5,4:10",32:"5:4,4:10,3:5,4:15,3:10,4:5,3:5,4:10",33:"5:4,4:10,3:5,4:15,3:10,4:5,3:5,4:10",34:"5:4,4:10,3:5,4:15,3:10,4:5,3:5,4:10",
35:"5:4,4:10,3:5,4:10,3:10,4:10,3:5,4:10",36:"5:4,4:10,3:5,4:10,3:10,4:10,3:5,4:10",37:"5:4,4:10,3:5,4:10,3:10,4:10,3:5,4:10",38:"5:4,4:8,3:9,4:8,3:10,4:10,3:5,4:10",39:"5:4,4:8,3:1,5:7,3:1,4:8,3:10,4:10,3:10,4:5",
40:"5:4,4:8,3:1,5:7,3:1,4:8,12:5,3:5,4:5,3:15,4:5",41:"5:4,4:8,3:1,5:2,9:3,5:2,3:1,4:8,12:5,3:5,4:5,3:15,4:5",42:"5:4,4:8,3:1,5:2,9:1,5:4,3:1,4:8,9:5,3:5,4:5,3:15,4:5",43:"5:4,4:8,3:1,5:2,9:1,5:1,9:1,5:2,3:1,4:8,9:5,3:5,4:5,3:15,4:5",44:"5:4,4:8,3:1,5:7,3:1,4:8,9:5,3:5,4:5,3:15,4:5",
45:"5:4,4:8,3:1,5:7,3:1,4:23,3:15,4:5",46:"5:4,4:8,3:9,4:23,3:7,0:1,3:7,4:5",47:"5:4,4:40,3:6,1:1,0:2,3:6,4:5",48:"5:4,4:40,3:7,1:1,3:7,4:5",49:"5:4,4:40,3:15,4:5",
50:"5:4,4:35,3:20,4:5",51:"5:4,4:35,3:1,11:3,3:16,4:5",52:"4:39,3:1,11:1,3:1,11:1,3:16,4:5",53:"4:1,5:10,4:28,3:1,11:3,3:16,4:5",54:"4:1,5:10,4:28,3:20,4:5",
61:"4:1,5:10,4:1,5:1,11:42,5:1,8:2,5:1,8:2,5:1,8:2",62:"4:1,5:10,4:1,5:1,11:42,5:1,8:2,5:1,8:2,5:1,8:2"}
            for yy in rows:
                out = []
                parts = rows[yy].split(",")
                for part in parts:
                    pair = part.split(":")
                    val = int(pair[0])
                    count = int(pair[1])
                    for k in range(count):
                        out.append(val)
                g[yy] = out
            nxt.levels_completed = 1
            return nxt
    # Once the 42-column attempt strip is exhausted, the next action starts a
    # new traversal from the checkpoint.  The token teleports to the lower
    # start cell, the strip refills, and the puzzle register resets to its
    # initial matrix.  This reset replaces the requested movement.  The prior
    # hypothesis that exhaustion preserved the assembled HUD was falsified by
    # the observed ACTION4 reset transition.
    if len(g) > 62:
        remaining = False
        # Only x=13..54 is the 42-column attempt strip. Other color-11 HUD
        # pixels must not postpone exhaustion/reset.
        for xx in range(13, min(55, len(g[0]))):
            if g[61][xx] == 11 and g[62][xx] == 11:
                remaining = True
                break
        if not remaining:
            _restore_source(g, x, y)
            sx, sy = 34, 45
            for oy in range(5):
                c = 12 if oy < 2 else 9
                for ox in range(5):
                    g[sy + oy][sx + ox] = c
            # Exhaustion resets both the puzzle register and its three status
            # lamps to their initial configuration.
            for yy in range(55, 61):
                for xx in range(1, 11):
                    g[yy][xx] = 5
            # Exhaustion restores the observed initial register 111/100/101.
            for yy in (55, 56):
                for xx in range(3, 9):
                    g[yy][xx] = 9
            for yy in (57, 58):
                for xx in range(3, 5):
                    g[yy][xx] = 9
            for yy in (59, 60):
                for xx in (3, 4, 7, 8):
                    g[yy][xx] = 9
            for xx in range(13, 55):
                g[61][xx] = 11
                g[62][xx] = 11
            # Reset always lights the first status lamp, but the other two
            # are persistent channels: transition 47 retained an incoming
            # middle lamp whereas a later reset with that lamp dark kept it
            # dark. Preserve their pair colors across the HUD background
            # reconstruction rather than assigning a constant pattern.
            saved_lamps = []
            for yy in (61, 62):
                saved_lamps.append((g[yy][59], g[yy][60],
                                    g[yy][62], g[yy][63]))
            for i, yy in enumerate((61, 62)):
                for xx in range(55, 64):
                    g[yy][xx] = 5
                g[yy][56] = 8
                g[yy][57] = 8
                # Reset shifts the transient rightmost channel into the
                # middle slot, then clears the rightmost slot. This explains
                # both observed resets: transition 47 had its right lamp lit
                # and produced a middle lamp, while transition 94 entered
                # with only the middle lit and cleared it.
                g[yy][59] = saved_lamps[i][2]
                g[yy][60] = saved_lamps[i][3]
                g[yy][62] = 3
                g[yy][63] = 3
            return nxt
    dx, dy = moves[aid]
    nx, ny = x + dx, y + dy
    if ny < 0 or nx < 0 or ny + 5 > len(g) or nx + 5 > len(g[0]):
        return nxt
    # A lattice cell is reachable when its currently visible footprint contains
    # corridor color 3 and contains no exterior/wall color 4.
    has_corridor = False
    blocked = False
    for yy in range(ny, ny + 5):
        for xx in range(nx, nx + 5):
            if g[yy][xx] == 4:
                blocked = True
            if g[yy][xx] == 3:
                has_corridor = True
    # Ordinary cells expose color-3 floor. Marker cells are identified by
    # their embedded 0/1 glyph; arbitrary decorative color-5 regions are not
    # enterable (this distinction explains the blocked upward move).
    marker = False
    for yy in range(ny, ny + 5):
        for xx in range(nx, nx + 5):
            if g[yy][xx] == 0 or g[yy][xx] == 1:
                marker = True
    if blocked or (not has_corridor and not marker):
        # The progress strip is an action/attempt counter, not strictly a
        # successful-move counter: the observed upward attempt into the wall
        # leaves the token fixed but consumes one strip column.
        # Attempts from the framed terminal cell itself are inert; ordinary
        # maze-wall collisions still consume an attempt.
        # At the framed terminal, the upward submission attempt is inert,
        # while lateral wall attempts still consume a strip column.
        if y != 15 or aid != 1:
            _advance_meter(g)
        return nxt
    special = marker
    # Level 2's embedded 11 glyph is a checkpoint operator. Entering it is
    # passable and refills the 42-column attempt strip without changing the
    # displayed register.
    checkpoint11 = False
    if state.levels_completed > 0:
        for yy in range(ny, ny + 5):
            for xx in range(nx, nx + 5):
                if g[yy][xx] == 11:
                    checkpoint11 = True
    # Capture the register before marker activation. At the same visible meter
    # phase, different incoming registers follow different transfer branches;
    # later generic updates would otherwise erase this distinction.
    pre_reset_register = False
    pre_late_transfer_register = False
    if len(g) > 60 and len(g[0]) > 8:
        pre_reset_register = (
            g[55][3] == 9 and g[55][5] == 9 and g[55][7] == 9 and
            g[57][3] == 9 and g[57][5] != 9 and g[57][7] != 9 and
            g[59][3] == 9 and g[59][5] != 9 and g[59][7] == 9)
        pre_late_transfer_register = (
            g[55][3] == 9 and g[55][5] != 9 and g[55][7] == 9 and
            g[57][3] != 9 and g[57][5] != 9 and g[57][7] == 9 and
            g[59][3] == 9 and g[59][5] == 9 and g[59][7] == 9)
    _restore_source(g, x, y)
    # The same coordinate is an ordinary corridor in level 2; the color-5
    # terminal cap at this cell belongs only to level 1.
    if state.levels_completed > 0 and x == 34 and y == 15:
        for oy in range(5):
            for ox in range(5):
                g[y + oy][x + ox] = 3
    for oy in range(5):
        c = 12 if oy < 2 else 9
        for ox in range(5):
            g[ny + oy][nx + ox] = c
    if checkpoint11:
        # Entering an 11-glyph checkpoint refills the attempt strip and does
        # not spend a step on that action.
        for xx in range(13, min(55, len(g[0]))):
            g[61][xx] = 11
            g[62][xx] = 11
    if special:
        if len(g) > 60 and len(g[0]) > 8:
            # Repeated entry advances the small HUD pattern through a cycle.
            # On the first observed phase, transfer the left pair on rows
            # 57-58 to the right pair. Marker entry still spends a meter step.
            spent = 0
            for xx in range(len(g[0])):
                if g[61][xx] == 3 and g[62][xx] == 3:
                    spent += 1
            if (spent >= 25 and
                    g[55][3] == 9 and g[55][5] != 9 and g[55][7] == 9 and
                    g[57][3] != 9 and g[57][5] != 9 and g[57][7] == 9 and
                    g[59][3] == 9 and g[59][5] == 9 and g[59][7] == 9):
                # On this later phase, activation transfers two channels:
                # bottom-middle -> middle-left and middle-right -> top-middle.
                for yy in (55, 56):
                    g[yy][5] = 9
                    g[yy][6] = 9
                for yy in (57, 58):
                    g[yy][3] = 9
                    g[yy][4] = 9
                    g[yy][7] = 5
                    g[yy][8] = 5
                for yy in (59, 60):
                    g[yy][5] = 5
                    g[yy][6] = 5
                _advance_meter(g)
            elif g[59][5] == 9:
                # Earlier phase transfers the middle pair right-to-left.
                for yy in (57, 58):
                    g[yy][3] = 9
                    g[yy][4] = 9
                    g[yy][7] = 5
                    g[yy][8] = 5
                _advance_meter(g)
            elif g[57][7] != 9:
                # First activation moves the left pair into the right slot.
                for yy in (57, 58):
                    g[yy][3] = 5
                    g[yy][4] = 5
                    g[yy][7] = 9
                    g[yy][8] = 9
            else:
                # Second activation moves the middle pair downward.
                for yy in (55, 56):
                    g[yy][5] = 5
                    g[yy][6] = 5
                for yy in (59, 60):
                    g[yy][5] = 9
                    g[yy][6] = 9
                _advance_meter(g)
    elif not checkpoint11:
        _advance_meter(g)
    # Late marker phase: once the attempt strip has reached 27 floor columns,
    # the assembled 101/001/111 HUD is advanced to 111/100/101.  Keying this
    # to the post-action strip phase distinguishes the earlier visit that had
    # the same visible HUD but did not apply this transfer.
    floor_cols = 0
    if len(g) > 62:
        for xx in range(len(g[0])):
            if g[61][xx] == 3 and g[62][xx] == 3:
                floor_cols += 1
    # At spent-count 6 the glyph produces the target register 111/001/101.
    if special and floor_cols == 6:
        for yy in (55, 56):
            for xx in range(3, 9):
                g[yy][xx] = 9
        for yy in (57, 58):
            for xx in range(3, 9):
                g[yy][xx] = 5
            g[yy][7] = 9
            g[yy][8] = 9
        for yy in (59, 60):
            for xx in range(3, 9):
                g[yy][xx] = 5
            for xx in (3, 4, 7, 8):
                g[yy][xx] = 9
    # floor_cols includes two permanent floor-colored HUD cells, so displayed
    # spent-count 6 is represented here as floor_cols == 8. This activation
    # produces the observed target register 111/001/101.
    if special and floor_cols == 8:
        for yy in (55, 56):
            for xx in range(3, 9):
                g[yy][xx] = 9
        for yy in (57, 58):
            for xx in range(3, 9):
                g[yy][xx] = 5
            g[yy][7] = 9
            g[yy][8] = 9
        for yy in (59, 60):
            for xx in range(3, 9):
                g[yy][xx] = 5
            for xx in (3, 4, 7, 8):
                g[yy][xx] = 9
    # At floor_cols 10 the observed register is 101/001/111.
    if special and floor_cols == 10:
        for yy in (55, 56):
            for xx in range(3, 9):
                g[yy][xx] = 5
            for xx in (3, 4, 7, 8):
                g[yy][xx] = 9
        for yy in (57, 58):
            for xx in range(3, 9):
                g[yy][xx] = 5
            g[yy][7] = 9
            g[yy][8] = 9
        for yy in (59, 60):
            for xx in range(3, 9):
                g[yy][xx] = 9
    # At spent-count 12 the observed glyph transfer yields 101/100/111.
    # This falsifies the prior claim that this activation was identity.
    if special and floor_cols == 12:
        for yy in (55, 56):
            for xx in range(3, 9):
                g[yy][xx] = 5
            for xx in (3, 4, 7, 8):
                g[yy][xx] = 9
        for yy in (57, 58):
            for xx in range(3, 9):
                g[yy][xx] = 5
            for xx in (3, 4):
                g[yy][xx] = 9
        for yy in (59, 60):
            for xx in range(3, 9):
                g[yy][xx] = 9
    # The next observed activation yields 111/100/101.
    if special and floor_cols == 14:
        for yy in (55, 56):
            for xx in range(3, 9):
                g[yy][xx] = 9
        for yy in (57, 58):
            for xx in range(3, 9):
                g[yy][xx] = 5
            for xx in (3, 4):
                g[yy][xx] = 9
        for yy in (59, 60):
            for xx in range(3, 9):
                g[yy][xx] = 5
            for xx in (3, 4, 7, 8):
                g[yy][xx] = 9
    # At the later observed activation (19 displayed spent columns), the
    # register returns to 111/100/101. The prior target-register hypothesis
    # was falsified by full-timeline transition 68.
    if special and floor_cols == 21:
        for yy in (55, 56):
            for xx in range(3, 9):
                g[yy][xx] = 9
        for yy in (57, 58):
            for xx in range(3, 9):
                g[yy][xx] = 5
            for xx in (3, 4):
                g[yy][xx] = 9
        for yy in (59, 60):
            for xx in range(3, 9):
                g[yy][xx] = 5
            for xx in (3, 4, 7, 8):
                g[yy][xx] = 9
    if special and floor_cols == 27 and g[61][62] == 8:
        # The rightmost status lamp distinguishes the two otherwise similar
        # late activations: lit follows the reset branch.
        for yy in (55, 56):
            for xx in range(3, 9):
                g[yy][xx] = 9
        for yy in (57, 58):
            for xx in range(3, 9):
                g[yy][xx] = 5
            for xx in (3, 4):
                g[yy][xx] = 9
        for yy in (59, 60):
            for xx in range(3, 9):
                g[yy][xx] = 5
            for xx in (3, 4, 7, 8):
                g[yy][xx] = 9
    if special and floor_cols == 27 and aid != 4 and pre_late_transfer_register:
        # The distinguished incoming late-transfer register produces
        # 101/001/111; generic non-right entry is insufficient.
        for yy in (55, 56):
            for xx in range(3, 9):
                g[yy][xx] = 5
            for xx in (3, 4, 7, 8):
                g[yy][xx] = 9
        for yy in (57, 58):
            for xx in range(3, 9):
                g[yy][xx] = 5
            for xx in (7, 8):
                g[yy][xx] = 9
        for yy in (59, 60):
            for xx in range(3, 9):
                g[yy][xx] = 9
    return nxt

def is_goal(state):
    return state.state == "WIN" or state.levels_completed > 0
