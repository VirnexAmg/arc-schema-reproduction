# Grid navigation hypothesis: a fixed 5x5 token moves on color-3 track tiles.
# ACTION1 is up and ACTION2 is down from observed transitions.
# ACTION1=up, ACTION2=down, and ACTION3=left from observed transitions; ACTION4 is inferred right.

def _token_box(g):
    # Color 12 may occur in both the movable token and an upper goal image.
    # Treat disconnected 12 regions separately and prefer the lowest complete
    # 2x5 cap that has the token's three 9-colored rows immediately below it.
    seen = []
    candidates = []
    for y in range(len(g)):
        for x in range(len(g[y])):
            if g[y][x] != 12 or (y, x) in seen:
                continue
            stack = [(y, x)]
            comp = []
            seen.append((y, x))
            while stack:
                cy, cx = stack.pop()
                comp.append((cy, cx))
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    py, px = cy + dy, cx + dx
                    if (py >= 0 and py < len(g) and px >= 0 and
                            px < len(g[py]) and g[py][px] == 12 and
                            (py, px) not in seen):
                        seen.append((py, px))
                        stack.append((py, px))
            y0 = min(p[0] for p in comp)
            y1 = max(p[0] for p in comp)
            x0 = min(p[1] for p in comp)
            x1 = max(p[1] for p in comp)
            if len(comp) == 10 and y1 == y0 + 1 and x1 == x0 + 4:
                body = True
                if y0 + 4 >= len(g):
                    body = False
                else:
                    for yy in range(y0 + 2, y0 + 5):
                        for xx in range(x0, x0 + 5):
                            if g[yy][xx] != 9:
                                body = False
                if body:
                    candidates.append((y0, x0))
    # The same token can occupy either the lower corridors or the upper target
    # chamber; there is normally only one complete 12/9 token silhouette.
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1]


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

    # A downward traversal immediately following the upward control state is
    # refunded. The prior model correctly recognized this status but wrongly
    # charged the return traversal.
    refund_down = False
    if aid == 2 and len(g) > 59 and len(g[55]) > 8:
        top_now = tuple(g[55][3 + i] for i in range(6))
        bottom_now = tuple(g[59][3 + i] for i in range(6))
        # The observed pre-return (upward) status has a solid top band and
        # split bottom band.  The previous test accidentally reversed these
        # two bands, so the historical downward return was charged.
        refund_down = (top_now == (9, 9, 9, 9, 9, 9) and
                       bottom_now == (9, 9, 5, 5, 9, 9))

    touched_glyph = False
    for y in range(ny, ny + 5):
        for x in range(nx, nx + 5):
            # The route can cross both color-3 corridor and color-5 room floor.
            # Small 0/1 floor glyphs are traversable controls.
            if g[y][x] == 0 or g[y][x] == 1:
                touched_glyph = True
            if g[y][x] not in (0, 1, 3, 5):
                # Attempting to push into a wall/target leaves the token fixed
                # but still advances the two-row movement meter.
                # Recorded downward actions are meter-neutral, including when
                # the destination is blocked; other blocked directions spend.
                if aid != 2 and len(g) > 62:
                    for my in (61, 62):
                        for mx in range(len(g[my])):
                            if g[my][mx] == 11:
                                g[my][mx] = 3
                                break
                return nxt

    # The control can be visually absent in a replayed model state after it was
    # previously covered. Recognize its destination structurally: it occupies a
    # broad corridor immediately left of a five-cell vertical wall. Downward
    # entry still activates it and refunds the move even if its 0/1 pixels are
    # currently hidden/missing.
    if aid == 2 and nx + 15 < len(g[0]):
        # The stable landmark is the vertical wall three token-widths right of
        # the control destination; the token's left edge is x=19 and the wall
        # begins at x=34 in the observed layout.
        control_destination = True
        for yy in range(ny, ny + 5):
            if g[yy][nx + 15] != 4:
                control_destination = False
        if control_destination:
            touched_glyph = True

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
    # All recorded downward transitions are meter-neutral. Earlier apparent
    # charging was caused by attributing adjacent upward-action meter changes
    # to the return. This also covers downward movement away from the target.
    spend_progress = (aid != 2)
    if touched_glyph and len(g) > 60 and len(g[55]) > 8:
        update_status = True
        if aid == 2:
            # Every downward crossing refunds the movement cost and displays
            # the directional 111/100/101 status, even after an earlier
            # upward traversal.
            patterns = ((9, 9, 9, 9, 9, 9),
                        (9, 9, 5, 5, 5, 5),
                        (9, 9, 5, 5, 9, 9))
            spend_progress = False
        else:
            patterns = ((9, 9, 5, 5, 9, 9),
                        (5, 5, 5, 5, 9, 9),
                        (9, 9, 9, 9, 9, 9))
        if update_status:
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
