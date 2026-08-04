"""Row-major fill-bar theory inferred from the first observed transition."""


def init_state(entry_grid):
    return {"turn": 0}


def _is_full(grid):
    return bool(grid) and all(row and all(value == 1 for value in row) for row in grid)


def predict(latent, grid, action):
    action_id = int(action["id"])
    next_grid = deepcopy(grid)
    next_latent = deepcopy(latent)
    next_latent["turn"] = latent["turn"] + 1
    next_latent["last_action"] = action_id

    if action_id == 1:
        placed = False
        for row in next_grid:
            for x in range(len(row)):
                if row[x] == 0:
                    row[x] = 1
                    placed = True
                    break
            if placed:
                break

    events = ["WIN"] if _is_full(next_grid) else []
    return next_grid, events, next_latent


def is_goal(latent, grid):
    return _is_full(grid)
