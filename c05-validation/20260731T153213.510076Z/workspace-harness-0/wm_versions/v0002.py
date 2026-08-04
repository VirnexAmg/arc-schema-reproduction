"""Conservative model for the initial, visually featureless state.

Until a transition is observed, actions are modeled as having no visible effect.
The latent turn count supports a small hidden-state extension once evidence arrives.
"""


def init_state(entry_grid):
    width = len(entry_grid[0]) if entry_grid else 0
    return {"turn": 0, "height": len(entry_grid), "width": width}


def predict(latent, grid, action):
    action_id = int(action["id"])
    next_grid = deepcopy(grid)
    next_latent = deepcopy(latent)
    next_latent["turn"] = latent["turn"] + 1
    next_latent["last_action"] = action_id
    return next_grid, [], next_latent


def is_goal(latent, grid):
    return False
