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
        # Corridors and special endpoint floors continue horizontally.
        if left == right:
            floor = left
        elif left != 4:
            floor = left
        else:
            floor = right
        for dx in range(5):
            g[y + dy][x + dx] = floor

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
    g = nxt.grid
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
    if blocked or not has_corridor:
        return nxt
    _restore_source(g, x, y)
    for oy in range(5):
        c = 12 if oy < 2 else 9
        for ox in range(5):
            g[ny + oy][nx + ox] = c
    _advance_meter(g)
    return nxt

def is_goal(state):
    return state.state == "WIN" or state.levels_completed > 0
