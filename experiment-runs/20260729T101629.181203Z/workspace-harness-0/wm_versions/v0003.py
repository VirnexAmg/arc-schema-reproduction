def init_state(entry_grid):
    return {}

def predict(latent, grid, action):
    g = deepcopy(grid)
    aid = int(action["id"])
    pts = []
    for y, row in enumerate(g):
        for x, v in enumerate(row):
            if v == 12:
                pts.append((x, y))
    if pts:
        x0 = min(p[0] for p in pts)
        y0 = min(p[1] for p in pts)
        move = {1:(0,-5), 2:(0,5), 3:(-5,0), 4:(5,0)}
        dx, dy = move[aid]
        nx, ny = x0 + dx, y0 + dy
        ok = 0 <= ny and ny + 4 < len(g) and 0 <= nx and nx + 4 < len(g[0])
        if ok:
            for yy in range(ny, ny + 5):
                for xx in range(nx, nx + 5):
                    # Gray (5) cells in the small top socket are enterable too;
                    # the observed player moved from y=20 to y=15 across that border.
                    if g[yy][xx] not in (3, 5, 9, 12):
                        ok = False
        if ok:
            for yy in range(y0, y0 + 5):
                for xx in range(x0, x0 + 5):
                    g[yy][xx] = 3
            for yy in range(ny, ny + 5):
                for xx in range(nx, nx + 5):
                    g[yy][xx] = 12 if yy < ny + 2 else 9
    for y in (61, 62):
        if y < len(g):
            for x, v in enumerate(g[y]):
                if v == 11:
                    g[y][x] = 3
                    break
    return g, [], latent

def is_goal(latent, grid):
    return False
