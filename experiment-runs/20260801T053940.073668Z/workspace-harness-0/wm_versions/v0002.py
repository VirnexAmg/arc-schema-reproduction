# Initial observation model. Action effects remain deliberately ungrounded until
# the first transition: action ids are not assigned meanings from convention.

def _cells(grid, colors):
    out = []
    for r, row in enumerate(grid):
        for c, value in enumerate(row):
            if value in colors:
                out.append((r, c, value))
    return out


def init_state(entry_grid):
    return {
        "marker": _cells(entry_grid, (0, 1)),
        "target": _cells(entry_grid, (12,)),
        "observed_actions": {},
    }


def predict(latent, grid, action):
    # Identity is the only evidence-safe pre-transition prediction. A mismatch
    # from exploration will ground the probed action's actual effect.
    aid = int(action["id"])
    nxt_latent = deepcopy(latent)
    nxt_latent["observed_actions"][aid] = "probed"
    return deepcopy(grid), [], nxt_latent


def is_goal(latent, grid):
    # No level boundary has yet been observed; never manufacture one for BFS.
    return False
