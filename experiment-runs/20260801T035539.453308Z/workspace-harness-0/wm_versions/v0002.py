# Initial conservative model for the unprobed entry frame.
# Visible objects are grounded, but controls and boundary events are unknown.

def init_state(entry_grid):
    return {"probes": 0, "last_action": None}


def predict(latent, grid, action):
    """Until a control is observed, predict no visible or boundary change."""
    aid = int(action["id"])
    nxt_latent = {
        "probes": latent["probes"] + 1,
        "last_action": aid,
    }
    return deepcopy(grid), [], nxt_latent


def is_goal(latent, grid):
    # Require evidence of a real level boundary before modeling completion.
    return False
