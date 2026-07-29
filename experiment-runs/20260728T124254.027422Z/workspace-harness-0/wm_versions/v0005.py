# Grid navigation hypothesis: a fixed 5x5 token moves on color-3 track tiles.
# ACTION1 is up and ACTION2 is down from observed transitions.
# ACTION3/4 are provisional left/right hypotheses pending an experiment.

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

    for y in range(ny, ny + 5):
        for x in range(nx, nx + 5):
            # The route can cross both color-3 corridor and color-5 room floor.
            # Other colors are obstacles; this explains the stop before the patterned icon.
            if g[y][x] != 3 and g[y][x] != 5:
                return nxt

    for y in range(y0, y0 + 5):
        for x in range(x0, x0 + 5):
            g[y][x] = 3
    for y in range(ny, ny + 2):
        for x in range(nx, nx + 5):
            g[y][x] = 12
    for y in range(ny + 2, ny + 5):
        for x in range(nx, nx + 5):
            g[y][x] = 9

    # Successful moves advance the two-row progress strip by one pixel.
    if len(g) > 62:
        for y in (61, 62):
            for x in range(len(g[y])):
                if g[y][x] == 11:
                    g[y][x] = 3
                    break
    return nxt


def is_goal(state):
    return state.state == "WIN" or state.levels_completed > 0
