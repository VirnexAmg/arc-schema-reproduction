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
    if x == 20 and y == 30:
        g[y + 1][x + 2] = 0
        g[y + 2][x + 1] = 1
        g[y + 2][x + 2] = 0
        g[y + 2][x + 3] = 0
        g[y + 3][x + 2] = 1

def _advance_meter(g):
    # Rows 61-62 contain a left-to-right progress strip of colors 3 then 11.
    if len(g) <= 62:
        return
    w = len(g[0])
    for x in range(w):
        if g[61][x] == 11 and g[62][x] == 11:
            g[61][x] = 3
            g[62][x] = 3
            return

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
        return nxt
    special = marker
    _restore_source(g, x, y)
    for oy in range(5):
        c = 12 if oy < 2 else 9
        for ox in range(5):
            g[ny + oy][nx + ox] = c
    if special:
        # Entering the glyph consumes the currently active lower HUD segment;
        # the already-lit segment at x=7..8 remains unchanged.
        if len(g) > 58 and len(g[0]) > 4:
            for yy in (57, 58):
                g[yy][3] = 5
                g[yy][4] = 5
                g[yy][7] = 9
                g[yy][8] = 9
    else:
        _advance_meter(g)
    return nxt

def is_goal(state):
    return state.state == "WIN" or state.levels_completed > 0
