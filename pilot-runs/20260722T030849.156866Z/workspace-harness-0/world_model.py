# Schema-style world model for ls20-9607627b
# Helpers available: GridState, find_color, bbox, neighbors4, deepcopy

def step(state, action):
    """Return next GridState after applying action.
    
    From observed transitions:
    - Action 1 (id=1) moves the player (color 5) upward by 5 rows.
      The player is a 4x10 block of color 5 at the bottom (rows 52-61, cols 1-10).
      After action 1, the player block shifts up by 5 rows (to rows 47-56).
      The rest of the grid remains unchanged.
    - Other actions (2,3,4) are not yet observed, so we assume identity for now.
    """
    nxt = state.copy()
    
    if action == 1:
        # Move player (color 5) upward by 5 rows.
        # Find the player block: it's a 4x10 block of color 5 at the bottom.
        # We'll locate it by finding all cells of color 5 and computing bbox.
        player_cells = find_color(nxt, 5)
        if not player_cells:
            return nxt  # no player, nothing to move
        x0, y0, x1, y1 = bbox(player_cells)
        # The player is 10 wide, 4 tall. We'll move it up by 5.
        new_y0 = y0 - 5
        new_y1 = y1 - 5
        # Clear old player area
        for y in range(y0, y1+1):
            for x in range(x0, x1+1):
                nxt.grid[y][x] = 4  # background color
        # Draw player at new position
        for y in range(new_y0, new_y1+1):
            for x in range(x0, x1+1):
                nxt.grid[y][x] = 5
    # For other actions, identity for now.
    return nxt

def is_goal(state):
    # Goal condition: state is WIN or levels_completed > 0.
    # But we need to detect when the player reaches some goal area.
    # From the grid, there is a region of color 3 (green?) at the top.
    # Possibly the goal is to move the player into that region.
    # For now, use the default.
    return state.state == "WIN" or state.levels_completed > 0
