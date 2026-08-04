# Evidence-backed overlay-motion and glyph-station model.
# The color-12/9 payload occupies one 5x5 cell. Observed controls translate it
# in five-pixel increments. The blue/black station horizontally reflects the
# bottom status glyph without consuming the color-11 movement meter.

def _payload_anchor(grid):
    cells = []
    for r, row in enumerate(grid):
        for c, value in enumerate(row):
            if value == 12:
                cells.append((r, c))
    if not cells:
        return None
    return min(r for r, c in cells), min(c for r, c in cells)


def init_state(entry_grid):
    terrain = deepcopy(entry_grid)
    anchor = _payload_anchor(terrain)
    if anchor is not None:
        top, left = anchor
        for r in range(top, top + 5):
            for c in range(left, left + 5):
                terrain[r][c] = 3
    return {
        "steps": 0,
        "last_action": None,
        "terrain": terrain,
        "configured": False,
    }


def _move_payload(grid, terrain, row_delta, col_delta):
    anchor = _payload_anchor(grid)
    if anchor is None:
        return 0
    top, left = anchor
    if row_delta < 0 and top <= 15:
        return 0
    new_top = top + row_delta
    new_left = left + col_delta
    if new_top < 0 or new_top + 5 > len(grid):
        return 0
    if new_left < 0 or new_left + 5 > len(grid[0]):
        return 0
    station = False
    for r in range(new_top, new_top + 5):
        for c in range(new_left, new_left + 5):
            value = terrain[r][c]
            if value not in (0, 1, 3, 5, 9):
                return 0
            if value in (0, 1):
                station = True
    payload = [grid[r][left:left + 5] for r in range(top, top + 5)]
    for r in range(top, top + 5):
        for c in range(left, left + 5):
            grid[r][c] = terrain[r][c]
    for rr in range(5):
        for cc in range(5):
            grid[new_top + rr][new_left + cc] = payload[rr][cc]
    if station:
        return 2
    return 1


def _advance_meter(grid):
    for row in grid:
        first = None
        count = 0
        for c, value in enumerate(row):
            if value == 11:
                if first is None:
                    first = c
                count += 1
        if first is not None and count >= 20:
            row[first] = 3


def _reflect_status_glyph(grid):
    # The status glyph is the lowermost color-9 bitmap. Reflect its occupied
    # cells within their own bounding box, preserving the surrounding panel.
    lower = len(grid) - 12
    cells = []
    for r in range(lower, len(grid)):
        for c, value in enumerate(grid[r]):
            if value == 9:
                cells.append((r, c))
    if not cells:
        return
    left = min(c for r, c in cells)
    right = max(c for r, c in cells)
    reflected = [(r, left + right - c) for r, c in cells]
    for r, c in cells:
        grid[r][c] = 5
    for r, c in reflected:
        grid[r][c] = 9


def predict(latent, grid, action):
    aid = int(action["id"])
    nxt = deepcopy(grid)
    result = 0
    if aid == 1:
        result = _move_payload(nxt, latent["terrain"], -5, 0)
    elif aid == 2:
        result = _move_payload(nxt, latent["terrain"], 5, 0)
    elif aid == 3:
        result = _move_payload(nxt, latent["terrain"], 0, -5)
    elif aid == 4:
        result = _move_payload(nxt, latent["terrain"], 0, 5)

    configured = latent["configured"]
    if result == 2:
        _reflect_status_glyph(nxt)
        configured = not configured
    elif result == 1:
        _advance_meter(nxt)

    events = []
    anchor = _payload_anchor(nxt)
    if result and configured and anchor is not None and anchor[0] == 15:
        events.append("LEVEL_COMPLETE")

    nxt_latent = {
        "steps": latent["steps"] + 1,
        "last_action": aid,
        "terrain": latent["terrain"],
        "configured": configured,
    }
    return nxt, events, nxt_latent


def is_goal(latent, grid):
    anchor = _payload_anchor(grid)
    return latent["configured"] and anchor is not None and anchor[0] == 15
