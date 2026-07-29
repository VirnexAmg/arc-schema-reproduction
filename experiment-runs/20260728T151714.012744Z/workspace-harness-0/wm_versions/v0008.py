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

    # Controls move by one 5-pixel tile: up, down, left, right.
    if aid == 1:
        nx, ny = x, y - 5
    elif aid == 2:
        nx, ny = x, y + 5
    elif aid == 3:
        nx, ny = x - 5, y
    elif aid == 4:
        nx, ny = x + 5, y
    else:
        return nxt

    if nx < 0 or ny < 0 or nx + 4 >= len(grid[0]) or ny + 4 >= len(grid):
        return nxt

    # Ordinary route tiles are color 3.  The patterned upper terminal has a
    # special docking tile at x=34..38,y=15..19: its first row is color 5 and
    # the remaining rows are route-colored.
    vals = []
    for yy in range(ny, ny + 5):
        for xx in range(nx, nx + 5):
            vals.append(grid[yy][xx])
    open_route = all(v == 3 for v in vals)
    # Small color-0/1 glyphs embedded in a route tile are collectibles and do
    # not block entry. The first observed glyph is on tile x=19..23,y=30..34.
    collectible_route = (all(v in (0, 1, 3) for v in vals) and
                         any(v in (0, 1) for v in vals))
    upper_dock = (ny == 15 and nx == 34 and
                  all(grid[15][xx] == 5 for xx in range(34, 39)) and
                  all(grid[yy][xx] == 3 for yy in range(16, 20)
                      for xx in range(34, 39)))

    if not open_route and not collectible_route and not upper_dock:
        # Recorded wall collisions consume a meter step.  Pressing farther up
        # while already docked at the upper terminal is instead a total no-op.
        if not (aid == 1 and y == 15):
            _advance_meter(grid)
        return nxt

    # Vacated route cells reveal color 3. The upper dock preserves its color-5
    # stripe beneath the token's first row.
    for yy in range(y, y + 5):
        for xx in range(x, x + 5):
            grid[yy][xx] = 5 if y == 15 and yy == 15 else 3

    # Draw the 5x5 token: two color-12 rows over three color-9 rows.
    for yy in range(ny, ny + 5):
        for xx in range(nx, nx + 5):
            grid[yy][xx] = 12 if yy < ny + 2 else 9

    if collectible_route:
        # Entering the embedded 0/1 hazard damages the status icon rather than
        # advancing the ordinary move meter. In the observed icon, the damaged
        # segment is the pair at columns 3..4 on rows 57..58.
        if len(grid) > 58 and len(grid[57]) > 8:
            # Crossing the hazard toggles which of the two two-pixel status
            # marks is lit: left mark extinguishes and right mark relights.
            for yy in (57, 58):
                grid[yy][3] = 5
                grid[yy][4] = 5
                grid[yy][7] = 9
                grid[yy][8] = 9
    else:
        _advance_meter(grid)
    return nxt


def is_goal(state):
    return state.state == "WIN" or state.levels_completed > 0
