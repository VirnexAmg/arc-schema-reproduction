# Conservative latent model for the first probe.
# The black/blue 3x3 motif inside the green structure is the likely controllable
# object. Action meanings remain unassigned until a transition grounds one.

def _actor_cells(grid):
    cells = []
    for r in range(len(grid)):
        for c in range(len(grid[r])):
            if grid[r][c] == 0 or grid[r][c] == 1:
                cells.append((r, c, grid[r][c]))
    return cells


def init_state(entry_grid):
    return {"actor": _actor_cells(entry_grid), "moves": {}}


def predict(latent, grid, action):
    # With no observed transition, identity is the only evidence-safe prediction.
    # The next observed delta will ground an action-to-motion entry in moves.
    nxt = deepcopy(grid)
    out = deepcopy(latent)
    return nxt, [], out


def is_goal(latent, grid):
    return False
