# Schema-style world model for ls20-9607627b
# Helpers available: GridState, find_color, bbox, neighbors4, deepcopy

def find_block(state, color):
    """Return (y, x) of the first occurrence of a horizontal block of given color, or None."""
    grid = state.frame
    height = len(grid)
    width = len(grid[0]) if height > 0 else 0
    for y in range(height):
        for x in range(width):
            if grid[y][x] == color:
                if x + 4 < width and all(grid[y][x+i] == color for i in range(5)):
                    return (y, x)
    return None

def step(state, action):
    nxt = state.copy()
    action_id = int(action["id"])
    grid = nxt.frame
    height = len(grid)
    width = len(grid[0]) if height > 0 else 0
    
    # Find the 12 and 9 blocks
    pos12 = find_block(nxt, 12)
    pos9 = find_block(nxt, 9)
    
    if pos12 is None or pos9 is None:
        return nxt
    
    y12, x12 = pos12
    y9, x9 = pos9
    
    # Determine delta based on action
    if action_id == 1:
        delta = -5  # move up
    elif action_id == 2:
        delta = 5   # move down
    elif action_id == 3:
        delta = 0   # no vertical movement
    elif action_id == 4:
        delta = 0   # unknown, assume no movement for now
    else:
        delta = 0
    
    new_y12 = y12 + delta
    new_y9 = y9 + delta
    
    # Boundary check: blocks must stay within grid
    if new_y12 < 0 or new_y12 + 4 >= height:
        return nxt
    
    # Erase old blocks
    for y in range(y12, y12+2):
        for x in range(x12, x12+5):
            grid[y][x] = 3
    for y in range(y9, y9+3):
        for x in range(x9, x9+5):
            grid[y][x] = 3
    
    # Draw new blocks
    for y in range(new_y12, new_y12+2):
        for x in range(x12, x12+5):
            grid[y][x] = 12
    for y in range(new_y9, new_y9+3):
        for x in range(x9, x9+5):
            grid[y][x] = 9
    
    # Update counter: all actions increment the 3 counter by 1 (decrement 11 by 1)
    # The counter is in rows 61 and 62, starting at column 13.
    y_counter = 61
    # Find the start of the 3 block or 11 block
    # The pattern before the counter: 4:1,5:10,4:1,5:1 -> total 13 columns (0-12)
    # So column 13 is where the 3 or 11 starts.
    x_start = 13
    # Check if there is a 3 at x_start
    if grid[y_counter][x_start] == 3:
        # There is already a 3 block, find its end
        count3 = 0
        while x_start + count3 < width and grid[y_counter][x_start + count3] == 3:
            count3 += 1
        x_11 = x_start + count3
        # Set the first 11 to 3
        if x_11 < width and grid[y_counter][x_11] == 11:
            grid[y_counter][x_11] = 3
            grid[62][x_11] = 3
    else:
        # No 3 yet, so the 11 block starts at x_start
        # Set the first 11 to 3
        if grid[y_counter][x_start] == 11:
            grid[y_counter][x_start] = 3
            grid[62][x_start] = 3
    
    return nxt

def is_goal(state):
    return state.state == "WIN" or state.levels_completed > 0
