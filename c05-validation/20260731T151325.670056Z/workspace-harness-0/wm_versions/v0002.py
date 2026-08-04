# World model stub. Prefer the latent/event API for new theories:
#   init_state(entry_grid)
#   predict(latent, grid, action) -> (next_grid, events, next_latent)
#   is_goal(latent, grid)
# Legacy step(GridState, action) remains supported.
# Generic helpers: GridState, find_color, bbox, neighbors4, crop_frame,
# rotate90, connected_components, deepcopy.

def init_state(entry_grid):
    return {}


def predict(latent, grid, action):
    """Model only transitions grounded in the recorded timeline."""
    nxt = deepcopy(grid)
    aid = int(action["id"])
    if aid == 1 and nxt and nxt[0]:
        # Observed from the blank entry frame: ACTION1 marks the left cell.
        nxt[0][0] = 1
    return nxt, [], deepcopy(latent)


def is_goal(latent, grid):
    return False
