# Object-level motion model grounded by transition 1.
# The 12/9 five-cell tile is movable; ACTION1 translates it upward by its width.

def _cells(grid, colors):
    out = []
    for r, row in enumerate(grid):
        for c, value in enumerate(row):
            if value in colors:
                out.append((r, c, value))
    return out


def _target_box(grid):
    cells = _cells(grid, (12,))
    if not cells:
        return None
    rows = [cell[0] for cell in cells]
    cols = [cell[1] for cell in cells]
    c0 = min(cols)
    size = max(cols) - c0 + 1
    return min(rows), c0, size


def _move_target(grid, dr, dc):
    box = _target_box(grid)
    if box is None:
        return False
    r0, c0, size = box
    nr0 = r0 + dr
    nc0 = c0 + dc
    if nr0 < 0 or nc0 < 0:
        return False
    if nr0 + size > len(grid) or nc0 + size > len(grid[0]):
        return False
    for r in range(nr0, nr0 + size):
        for c in range(nc0, nc0 + size):
            if grid[r][c] != 3:
                return False
    payload = []
    for r in range(r0, r0 + size):
        payload.append(grid[r][c0:c0 + size])
    for r in range(r0, r0 + size):
        for c in range(c0, c0 + size):
            grid[r][c] = 3
    for rr in range(size):
        for cc in range(size):
            grid[nr0 + rr][nc0 + cc] = payload[rr][cc]
    return True


def _advance_bar(grid):
    # Each successful observed move replaced the leftmost 11 in both bar rows
    # with floor color 3.
    for row in grid:
        for c, value in enumerate(row):
            if value == 11:
                row[c] = 3
                break


def init_state(entry_grid):
    return {
        "target": _cells(entry_grid, (12,)),
        "observed_actions": {1: "target up"},
        "last_move": None,
    }


def predict(latent, grid, action):
    aid = int(action["id"])
    nxt = deepcopy(grid)
    moved = False
    if aid == 1:
        box = _target_box(nxt)
        if box is not None:
            moved = _move_target(nxt, -box[2], 0)
    if moved:
        _advance_bar(nxt)
    nxt_latent = deepcopy(latent)
    nxt_latent["target"] = _cells(nxt, (12,))
    nxt_latent["last_move"] = (aid, moved)
    return nxt, [], nxt_latent


def is_goal(latent, grid):
    # The interaction that completes a level is not observed yet.
    return False
