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
                    # Static dark-red (9) glyph cells are solid. Gray (5) socket
                    # floor is enterable, but the deeper move is blocked by the glyph.
                    v = g[yy][xx]
                    # The dark lower part of the player overlaps its own next
                    # footprint and is not an obstacle.  Small dark glyphs in
                    # the corridor are also enterable switches; large dark
                    # target glyphs remain solid.
                    own = x0 <= xx < x0 + 5 and y0 <= yy < y0 + 5
                    if v not in (3, 5, 12) and not (v == 9 and own):
                        ok = False
            if not ok:
                foreign_dark = 0
                bad_other = False
                for yy in range(ny, ny + 5):
                    for xx in range(nx, nx + 5):
                        v = g[yy][xx]
                        own = x0 <= xx < x0 + 5 and y0 <= yy < y0 + 5
                        if v == 9 and not own:
                            foreign_dark += 1
                        elif v not in (3, 5, 9, 12):
                            bad_other = True
                # Corridor switches are tiny (at most six pixels), unlike the
                # solid target glyph.
                # Sparse glyphs are switches only when embedded in the green
                # corridor. The top glyph sits on gray socket floor and stays
                # solid despite also having few dark pixels.
                on_gray = False
                for yy in range(ny, ny + 5):
                    for xx in range(nx, nx + 5):
                        if g[yy][xx] == 5:
                            on_gray = True
                if foreign_dark and foreign_dark <= 6 and not bad_other and not on_gray:
                    ok = True
                    for yy in (57, 58):
                        if yy < len(g):
                            for xx in range(3, 7):
                                g[yy][xx] = 5
        if ok:
            for yy in range(y0, y0 + 5):
                for xx in range(x0, x0 + 5):
                    # The socket entrance has a one-pixel gray lip beneath the
                    # player's top row; ordinary corridor floor is green.
                    g[yy][xx] = 5 if y0 == 15 and yy == 15 else 3
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
