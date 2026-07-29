# Schema-style world model stub. Replace step/is_goal with real hypotheses.
# Helpers available: GridState, find_color, bbox, neighbors4, deepcopy

def step(state, action):
    """Return next GridState. Must not invent levels without evidence."""
    nxt = state.copy()
    # Default: identity transition (safe but not useful for planning).
    return nxt

def is_goal(state):
    return state.state == "WIN" or state.levels_completed > 0
