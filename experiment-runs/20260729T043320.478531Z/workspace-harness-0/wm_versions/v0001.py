# World model stub. Prefer the latent/event API for new theories:
#   init_state(entry_grid)
#   predict(latent, grid, action) -> (next_grid, events, next_latent)
#   is_goal(latent, grid)
# Legacy step(GridState, action) remains supported.
# Generic helpers: GridState, find_color, bbox, neighbors4, crop_frame,
# rotate90, connected_components, deepcopy.

def step(state, action):
    """Return next GridState. Must not invent levels without evidence."""
    nxt = state.copy()
    # Default: identity transition (safe but not useful for planning).
    return nxt

def is_goal(state):
    return state.state == "WIN" or state.levels_completed > 0
