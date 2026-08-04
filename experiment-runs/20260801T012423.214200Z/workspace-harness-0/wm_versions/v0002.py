# Evidence-grounded baseline for the first action probe.
# No transition yet establishes action semantics, displacement, or redraw rules.

def init_state(entry_grid):
    return {"observed_actions": 0, "boundary_seen": False}


def predict(latent, grid, action):
    action_id = int(action["id"])
    nxt = deepcopy(grid)
    new_latent = deepcopy(latent)
    new_latent["last_action"] = action_id
    new_latent["observed_actions"] = latent["observed_actions"] + 1
    return nxt, [], new_latent


def is_goal(latent, grid):
    return bool(latent.get("boundary_seen", False))
