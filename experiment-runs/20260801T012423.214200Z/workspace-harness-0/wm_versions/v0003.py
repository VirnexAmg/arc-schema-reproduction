# Grid-grounded token model. Only action 1 has an observed motion effect.

def init_state(entry_grid):
    return {"at_goal": False, "last_action": None, "moved": False}


def _token_box(grid):
    cells = []
    for r in range(len(grid)):
        for c in range(len(grid[r])):
            if grid[r][c] == 12:
                cells.append((r, c))
    if not cells:
        return None
    return min(p[0] for p in cells), min(p[1] for p in cells)


def _drain_meter(grid):
    for r in range(len(grid)):
        cols = []
        for c in range(len(grid[r])):
            if grid[r][c] == 11:
                cols.append(c)
        if len(cols) >= 10:
            grid[r][min(cols)] = 3


def predict(latent, grid, action):
    action_id = int(action["id"])
    nxt = deepcopy(grid)
    moved = False
    reached = False
    box = _token_box(grid)

    # Transition 1 shows action 1 moving the 5x5 12/9 token upward by one
    # maze cell. Other action effects remain identity until observed.
    if box is not None and action_id == 1:
        top, left = box
        new_top = top - 5
        tile = []
        for rr in range(top, top + 5):
            tile.append([grid[rr][cc] for cc in range(left, left + 5)])
        open_dest = new_top >= 0
        if open_dest:
            for rr in range(new_top, new_top + 5):
                for cc in range(left, left + 5):
                    if grid[rr][cc] not in (0, 1, 3):
                        open_dest = False
        if open_dest:
            for rr in range(top, top + 5):
                for cc in range(left, left + 5):
                    nxt[rr][cc] = 3
            for rr in range(new_top, new_top + 5):
                for cc in range(left, left + 5):
                    if grid[rr][cc] in (0, 1):
                        reached = True
                    nxt[rr][cc] = tile[rr - new_top][cc - left]
            moved = True

    # Both long color-11 HUD rows lose their leftmost cell on the observed turn.
    _drain_meter(nxt)
    new_latent = deepcopy(latent)
    new_latent["last_action"] = action_id
    new_latent["moved"] = moved
    new_latent["at_goal"] = reached
    events = ["LEVEL_COMPLETE"] if reached else []
    return nxt, events, new_latent


def is_goal(latent, grid):
    return bool(latent.get("at_goal", False))
