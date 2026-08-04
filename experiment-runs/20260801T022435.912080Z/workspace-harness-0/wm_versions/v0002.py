# Evidence-first latent model.
# The entry frame visually separates into an upper arena and a lower panel.
# No transition yet proves which object is controlled or what actions mean.

def init_state(entry_grid):
    return {
        "entry": deepcopy(entry_grid),
        "actions": [],
        "control_mode": "unknown",
    }


def predict(latent, grid, action):
    action_id = int(action["id"])
    nxt_latent = {
        "entry": latent["entry"],
        "actions": latent["actions"] + [action_id],
        "control_mode": latent["control_mode"],
    }
    return deepcopy(grid), [], nxt_latent


def is_goal(latent, grid):
    # Add boundary events only after observing a level transition.
    return False
