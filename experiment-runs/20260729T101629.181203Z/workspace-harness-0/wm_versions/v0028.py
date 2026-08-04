def init_state(entry_grid):
    markers = []
    for y, row in enumerate(entry_grid):
        for x, v in enumerate(row):
            if v in (0, 1):
                markers.append((x, y, v))
    # Keep a coarse layout signature so mechanisms can be re-grounded after a
    # level boundary instead of assuming the level-1 panel coordinates.
    return {"markers": markers, "entry": deepcopy(entry_grid),
            "layout_signature": (len(entry_grid), len(entry_grid[0]),
                                 sum(1 for row in entry_grid for v in row if v == 0),
                                 sum(1 for row in entry_grid for v in row if v == 1))}

def predict(latent, grid, action):
    g = deepcopy(grid)
    aid = int(action["id"])
    # When the cyan countdown has no remaining dark (11) cells, the next
    # input respawns the player at the start and resets the status glyph.
    # This is an in-level timeout, not a GAME_OVER boundary.
    timer_left = False
    for yy in (61, 62):
        if yy < len(g) and 11 in g[yy]:
            timer_left = True
    if not timer_left:
        # Exhaustion restores the exact level-entry frame on the next input.
        # Using the grounded entry also preserves decorative timer end-caps.
        return deepcopy(latent["entry"]), [], latent
    recharged = False
    pts = []
    for y, row in enumerate(g):
        for x, v in enumerate(row):
            if v == 12:
                pts.append((x, y))
    if pts:
        x0 = min(p[0] for p in pts)
        y0 = min(p[1] for p in pts)
        # Once the lower-left 3x3 status matches the target glyph, pushing
        # upward from the socket entrance completes the level.  Compare the
        # three logical 2-pixel cells in each row (dark=1, gray=0).
        if aid == 1 and y0 == 15:
            status = []
            target = []
            for rr in range(3):
                sy = 55 + 2 * rr
                ty = 11 + rr
                status.append(tuple(1 if g[sy][3 + 2 * cc] == 9 else 0 for cc in range(3)))
                target.append(tuple(1 if g[ty][35 + cc] == 9 else 0 for cc in range(3)))
            if status == target:
                return g, ["LEVEL_COMPLETE"], latent
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
                    if v not in (0, 1, 3, 5, 12) and not (v == 9 and own):
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
                            # Contact clears the left 2x2 stroke of the
                            # bottom-left state glyph.
                            for xx in range(3, 5):
                                g[yy][xx] = 5
        if ok:
            for yy in range(y0, y0 + 5):
                for xx in range(x0, x0 + 5):
                    # The socket entrance has a one-pixel gray lip beneath the
                    # player's top row; ordinary corridor floor is green.
                    g[yy][xx] = 5 if y0 == 15 and yy == 15 else 3
            # Persistent tiny interaction glyph reappears when uncovered.
            for mx, my, mv in latent.get("markers", []):
                if y0 <= my < y0 + 5 and x0 <= mx < x0 + 5:
                    g[my][mx] = mv
            for yy in range(ny, ny + 5):
                for xx in range(nx, nx + 5):
                    g[yy][xx] = 12 if yy < ny + 2 else 9

            # Moving immediately beside the tiny black/blue corridor glyph
            # activates it.  The observable state change is the removal of a
            # 4x2 horizontal stroke from the large lower-left status glyph.
            near_small = False
            # Remember the tiny glyph even while the player visually covers it.
            # Its original 0/1 pixels are retained in latent state.
            marker_pts = latent.get("markers", [])
            for mx, my, mv in marker_pts:
                if nx - 1 <= mx <= nx + 5 and ny - 1 <= my <= ny + 5:
                    near_small = True
            if near_small:
                if aid in (1, 2):
                    # Vertical passage reflects the logical glyph left-right.
                    for yy in range(55, 61):
                        if yy < len(g):
                            a = g[yy][3]
                            b = g[yy][7]
                            for xx in (3, 4):
                                g[yy][xx] = b
                            for xx in (7, 8):
                                g[yy][xx] = a
                else:
                    # Horizontal passage reflects it top-bottom.
                    for off in range(2):
                        yt = 55 + off
                        yb = 59 + off
                        if yb < len(g):
                            for xx in range(3, 9):
                                g[yt][xx], g[yb][xx] = g[yb][xx], g[yt][xx]
                # In level 2, passage beside the upper transform glyph also
                # recharges the countdown.  The observed downward passage at
                # y=15 restored the entire 42-cell bar rather than merely
                # consuming its next two cells.  Level 1's lower glyph does
                # not satisfy this upper-corridor grounding.
                if ny <= 15:
                    recharged = True
                    for ty in (61, 62):
                        if ty < len(g):
                            for tx in range(14, 56):
                                g[ty][tx] = 11
    # Successful moves advance the countdown. At the narrow socket, blocked
    # sideways inputs also consume time, while the blocked upward target probe
    # leaves the frame unchanged (both behaviors are observed).
    if pts and (ok or aid in (2, 3, 4)) and not recharged:
        for y in (61, 62):
            if y < len(g):
                cleared = 0
                for x, v in enumerate(g[y]):
                    if v == 11:
                        g[y][x] = 3
                        cleared += 1
                        if cleared == 2:
                            break
    return g, [], latent

def is_goal(latent, grid):
    return False
