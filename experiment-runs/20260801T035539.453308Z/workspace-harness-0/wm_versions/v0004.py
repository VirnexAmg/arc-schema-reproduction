# Evidence-backed cell-motion model.
# The color-12/9 payload occupies one 5x5 maze cell. ACTION1 moves it
# upward by one cell when all destination pixels are color 3; a non-3
# destination is currently modeled as a blocked attempt.

def init_state(entry_grid):
    return {"steps": 0, "last_action": None}


def _payload_anchor(grid):
    cells = []
    for r, row in enumerate(grid):
        for c, value in enumerate(row):
            if value == 12:
                cells.append((r, c))
    if not cells:
        return None
    return min(r for r, c in cells), min(c for r, c in cells)


def _move_payload_up(grid):
    anchor = _payload_anchor(grid)
    if anchor is None:
        return
    top, left = anchor
    new_top = top - 5
    if new_top < 0:
        return
    for r in range(new_top, new_top + 5):
        for c in range(left, left + 5):
            if grid[r][c] != 3:
                return
    payload = [grid[r][left:left + 5] for r in range(top, top + 5)]
    for r in range(top, top + 5):
        for c in range(left, left + 5):
            grid[r][c] = 3
    for dr in range(5):
        for dc in range(5):
            grid[new_top + dr][left + dc] = payload[dr][dc]


def _advance_meter(grid):
    # Each real action consumes the leftmost cell of both long color-11 rows.
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
    if aid == 1:
        _move_payload_up(nxt)
    _advance_meter(nxt)
    nxt_latent = {"steps": latent["steps"] + 1, "last_action": aid}
    return nxt, [], nxt_latent


def is_goal(latent, grid):
    return False
