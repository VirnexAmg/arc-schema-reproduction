# Grid navigation hypothesis: a fixed 5x5 token moves on color-3 track tiles.
# ACTION1 is up and ACTION2 is down from observed transitions.
# ACTION1=up, ACTION2=down, and ACTION3=left from observed transitions; ACTION4 is inferred right.

def _token_box(g):
    pts = []
    for y in range(len(g)):
        for x in range(len(g[y])):
            if g[y][x] == 12:
                pts.append((y, x))
    if not pts:
        return None
    y0 = min(p[0] for p in pts)
    y1 = max(p[0] for p in pts)
    x0 = min(p[1] for p in pts)
    x1 = max(p[1] for p in pts)
    if y1 - y0 > 4 or x1 - x0 > 4:
        return None
    return (y0, x0)


def step(state, action):
    nxt = state.copy()
    g = nxt.frame
    pos = _token_box(g)
    if pos is None:
        return nxt

    aid = int(action["id"])
    moves = {1: (-5, 0), 2: (5, 0), 3: (0, -5), 4: (0, 5)}
    if aid not in moves:
        return nxt
    dy, dx = moves[aid]
    y0, x0 = pos
    ny, nx = y0 + dy, x0 + dx
    if ny < 0 or nx < 0 or ny + 5 > len(g) or nx + 5 > len(g[0]):
        return nxt

    touched_glyph = False
    for y in range(ny, ny + 5):
        for x in range(nx, nx + 5):
            # The route can cross both color-3 corridor and color-5 room floor.
            # Small 0/1 floor glyphs are traversable controls.
            if g[y][x] == 0 or g[y][x] == 1:
                touched_glyph = True
            if g[y][x] not in (0, 1, 3, 5):
                return nxt

    # Recover the covered background from the immediate horizontal border.
    # This preserves room-floor color 5 where the route crosses a room.
    for y in range(y0, y0 + 5):
        old = 3
        if x0 > 0 and (g[y][x0 - 1] == 3 or g[y][x0 - 1] == 5):
            old = g[y][x0 - 1]
        if x0 + 5 < len(g[y]) and g[y][x0 + 5] == 5:
            old = 5
        for x in range(x0, x0 + 5):
            g[y][x] = old
    # If a token leaves the activated control location, reveal its glyph again.
    # Recognize the location by the adjacent five-cell wall rather than absolute coordinates.
    if not touched_glyph and x0 + 10 < len(g[0]):
        control_site = True
        for yy in range(y0, y0 + 5):
            # Control lies in a broad corridor with floor immediately left and
            # a five-cell wall one token-width to the right.
            if g[yy][x0 + 10] != 4 or x0 == 0 or g[yy][x0 - 1] != 3:
                control_site = False
        if control_site:
            g[y0 + 1][x0 + 2] = 0
            g[y0 + 2][x0 + 1] = 1
            g[y0 + 2][x0 + 2] = 0
            g[y0 + 2][x0 + 3] = 0
            g[y0 + 3][x0 + 2] = 1

    for y in range(ny, ny + 2):
        for x in range(nx, nx + 5):
            g[y][x] = 12
    for y in range(ny + 2, ny + 5):
        for x in range(nx, nx + 5):
            g[y][x] = 9

    # Crossing the 0/1 control updates its directional status icon. Entering
    # from above grants/refunds the movement cost; entering from below does not.
    spend_progress = True
    if touched_glyph and len(g) > 60 and len(g[55]) > 8:
        if aid == 2:
            patterns = ((9, 9, 9, 9, 9, 9),
                        (5, 5, 5, 5, 9, 9),
                        (9, 9, 5, 5, 9, 9))
            spend_progress = False
        else:
            patterns = ((9, 9, 5, 5, 9, 9),
                        (5, 5, 5, 5, 9, 9),
                        (9, 9, 9, 9, 9, 9))
        for band in range(3):
            for yy in (55 + 2 * band, 56 + 2 * band):
                for i in range(6):
                    g[yy][3 + i] = patterns[band][i]
    if spend_progress and len(g) > 62:
        for y in (61, 62):
            for x in range(len(g[y])):
                if g[y][x] == 11:
                    g[y][x] = 3
                    break
    return nxt


def is_goal(state):
    return state.state == "WIN" or state.levels_completed > 0
