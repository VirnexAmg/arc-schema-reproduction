# Evidence-backed overlay-motion model.
# The color-12/9 payload occupies one 5x5 cell. ACTION1 moves it upward
# across traversable underlay colors; color 4 remains the blocking exterior.

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


def _move_payload_up(grid, terrain):
    anchor = _payload_anchor(grid)
    if anchor is None:
        return False
    top, left = anchor
    # The patterned core is a hard stop: the payload can occupy the lower
    # socket at row 15 but ACTION1 cannot translate it farther upward.
    if top <= 15:
        return False
    new_top = top - 5
    if new_top < 0:
        return False
    for r in range(new_top, new_top + 5):
        for c in range(left, left + 5):
            if terrain[r][c] not in (3, 5, 9):
                return False
    payload = [grid[r][left:left + 5] for r in range(top, top + 5)]
    for r in range(top, top + 5):
        for c in range(left, left + 5):
            grid[r][c] = terrain[r][c]
    for dr in range(5):
        for dc in range(5):
            grid[new_top + dr][left + dc] = payload[dr][dc]
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
        changed = _move_payload_up(nxt, latent["terrain"])
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
