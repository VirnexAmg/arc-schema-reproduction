# Grid world hypothesis: action 1 moves the 5x5 striped block one cell-unit
# (five pixels) upward. The lower panel records the chosen action.

def step(state, action):
    nxt = state.copy()
    g = nxt.frame
    aid = int(action["id"])

    # Locate the movable 5x5 block whose upper rows are color 12 and lower
    # rows color 9. Actions 1 and 2 are observed vertical tile moves.
    found = None
    h = len(g)
    w = len(g[0])
    for y in range(h - 4):
        for x in range(w - 4):
            ok = True
            for sy in range(5):
                expected = 12 if sy < 2 else 9
                for sx in range(5):
                    if g[y + sy][x + sx] != expected:
                        ok = False
            if ok:
                found = (x, y)
                break
        if found is not None:
            break

    # Observed controls: 1 moves up, 4 moves right, and 3 attempts left
    # (the recorded attempt was blocked by the wall). The remaining
    # symmetric control 2 is down.
    dx, dy = {1: (0, -5), 2: (0, 5), 3: (-5, 0), 4: (5, 0)}.get(aid, (0, 0))
    if found is not None and (dx != 0 or dy != 0):
        x, y = found
        nx, ny = x + dx, y + dy
        if 0 <= nx and nx + 4 < w and 0 <= ny and ny + 4 < h:
            clear = True
            for sy in range(5):
                for sx in range(5):
                    tx, ty = nx + sx, ny + sy
                    # Cells already occupied by the block do not obstruct
                    # horizontal/vertical translations. Ordinary corridor is 3.
                    if not (x <= tx < x + 5 and y <= ty < y + 5) and g[ty][tx] != 3:
                        clear = False
            if clear:
                for sy in range(5):
                    for sx in range(5):
                        g[y + sy][x + sx] = 3
                for sy in range(5):
                    c = 12 if sy < 2 else 9
                    for sx in range(5):
                        g[ny + sy][nx + sx] = c

    # Each accepted action advances the two-row meter by one pixel.
    if h > 62:
        for x in range(w):
            if g[61][x] == 11 and g[62][x] == 11:
                g[61][x] = 3
                g[62][x] = 3
                break

    return nxt


def is_goal(state):
    return state.state == "WIN" or state.levels_completed > 0
