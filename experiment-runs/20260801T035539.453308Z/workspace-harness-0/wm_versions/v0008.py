# Evidence-backed overlay-motion model.
# The color-12/9 payload occupies one 5x5 cell. Observed controls translate it
# in five-pixel increments across traversable underlay; color 4 blocks motion.

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
    return {"steps": 0, "last_action": None, "terrain": terrain}


def _move_payload(grid, terrain, row_delta, col_delta):
    anchor = _payload_anchor(grid)
    if anchor is None:
        return False
    top, left = anchor
    if row_delta < 0 and top <= 15:
        return False
    new_top = top + row_delta
    new_left = left + col_delta
    if new_top < 0 or new_top + 5 > len(grid):
        return False
    if new_left < 0 or new_left + 5 > len(grid[0]):
        return False
    for r in range(new_top, new_top + 5):
        for c in range(new_left, new_left + 5):
            if terrain[r][c] not in (3, 5, 9):
                return False
    payload = [grid[r][left:left + 5] for r in range(top, top + 5)]
    for r in range(top, top + 5):
        for c in range(left, left + 5):
            grid[r][c] = terrain[r][c]
    for rr in range(5):
        for cc in range(5):
            grid[new_top + rr][new_left + cc] = payload[rr][cc]
    return True


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


def predict(latent, grid, action):
    aid = int(action["id"])
    nxt = deepcopy(grid)
    changed = False
    if aid == 1:
        changed = _move_payload(nxt, latent["terrain"], -5, 0)
    elif aid == 2:
        changed = _move_payload(nxt, latent["terrain"], 5, 0)
    elif aid == 3:
        changed = _move_payload(nxt, latent["terrain"], 0, -5)
    if changed:
        _advance_meter(nxt)
    nxt_latent = {
        "steps": latent["steps"] + 1,
        "last_action": aid,
        "terrain": latent["terrain"],
    }
    return nxt, [], nxt_latent


def is_goal(latent, grid):
    return False
