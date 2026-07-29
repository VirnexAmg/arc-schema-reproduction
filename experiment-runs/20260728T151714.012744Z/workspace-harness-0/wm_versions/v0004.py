# Moving-token world model inferred from recorded transitions.
# Helpers available: GridState, find_color, bbox, neighbors4, deepcopy

def _token_box(grid):
    pts = []
    for y in range(len(grid)):
        for x in range(len(grid[y])):
            if grid[y][x] == 12:
                pts.append((x, y))
    if not pts:
        return None
    return (min(p[0] for p in pts), min(p[1] for p in pts))


def _advance_meter(grid):
    # Successful moves consume/advance the first color-11 meter column.
    if len(grid) <= 62:
        return
    w = len(grid[61])
    for x in range(w):
        if grid[61][x] == 11 and grid[62][x] == 11:
            grid[61][x] = 3
            grid[62][x] = 3
            return


def step(state, action):
    nxt = state.copy()
    grid = nxt.frame
    aid = int(action["id"])
    pos = _token_box(grid)
    if pos is None:
        return nxt
    x, y = pos

    # Transition evidence identifies ACTION1 as up and ACTION2 as down,
    # both by one 5-pixel cell. Other controls remain ungrounded.
    if aid == 1:
        ny = y - 5
        if y <= 15:
            return nxt
    elif aid == 2:
        ny = y + 5
        if ny + 4 >= len(grid):
            return nxt
    elif aid == 3:
        # At the observed vertical-lane position this control leaves the token
        # fixed but still advances the meter, unlike a blocked vertical move.
        _advance_meter(grid)
        return nxt
    else:
        return nxt

    # Vacated route cells reveal color 3. The top terminal has a preserved
    # color-5 stripe under the token's first row.
    for yy in range(y, y + 5):
        for xx in range(x, x + 5):
            grid[yy][xx] = 5 if y == 15 and yy == 15 else 3

    # Draw the 5x5 token: two color-12 rows over three color-9 rows.
    for yy in range(ny, ny + 5):
        for xx in range(x, x + 5):
            grid[yy][xx] = 12 if yy < ny + 2 else 9

    _advance_meter(grid)
    return nxt


def is_goal(state):
    return state.state == "WIN" or state.levels_completed > 0
