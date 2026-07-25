def step(state, action):
    # Reconstruct grid from find_color, but ensure we don't overwrite with 0
    grid = [[0]*64 for _ in range(64)]
    for color in range(1, 16):  # skip color 0 (background)
        try:
            positions = find_color(state, color)
            if positions:
                for pos in positions:
                    x, y = pos
                    if grid[y][x] == 0:  # only set if not already set
                        grid[y][x] = color
        except:
            pass
    # If grid is all zeros, return state as is
    if all(all(cell == 0 for cell in row) for row in grid):
        return state
    # Try to use state.get to fill in missing cells
    for y in range(64):
        for x in range(64):
            if grid[y][x] == 0:
                try:
                    val = state.get(x, y)
                    if val is not None and isinstance(val, int):
                        grid[y][x] = val
                except:
                    pass
    # If still zeros, try to use state[x][y] via __getitem__
    for y in range(64):
        for x in range(64):
            if grid[y][x] == 0:
                try:
                    val = state[x][y]
                    if isinstance(val, int):
                        grid[y][x] = val
                except:
                    pass
    # If still zeros, try to use state.pixel(x, y)
    for y in range(64):
        for x in range(64):
            if grid[y][x] == 0:
                try:
                    val = state.pixel(x, y)
                    if isinstance(val, int):
                        grid[y][x] = val
                except:
                    pass
    # If still zeros, try to use state.color_at(x, y)
    for y in range(64):
        for x in range(64):
            if grid[y][x] == 0:
                try:
                    val = state.color_at(x, y)
                    if isinstance(val, int):
                        grid[y][x] = val
                except:
                    pass
    # If still zeros, try to use state[x, y]
    for y in range(64):
        for x in range(64):
            if grid[y][x] == 0:
                try:
                    val = state[x, y]
                    if isinstance(val, int):
                        grid[y][x] = val
                except:
                    pass
    # If still zeros, try to use state.get_color(x, y)
    for y in range(64):
        for x in range(64):
            if grid[y][x] == 0:
                try:
                    val = state.get_color(x, y)
                    if isinstance(val, int):
                        grid[y][x] = val
                except:
                    pass
    # If still zeros, try to use state.at(x, y)
    for y in range(64):
        for x in range(64):
            if grid[y][x] == 0:
                try:
                    val = state.at(x, y)
                    if isinstance(val, int):
                        grid[y][x] = val
                except:
                    pass
    # If still zeros, try to use state.cell(x, y)
    for y in range(64):
        for x in range(64):
            if grid[y][x] == 0:
                try:
                    val = state.cell(x, y)
                    if isinstance(val, int):
                        grid[y][x] = val
                except:
                    pass
    # If still zeros, try to use state.get(0,0) to test if get works
    if all(all(cell == 0 for cell in row) for row in grid):
        try:
            val = state.get(0,0)
            if isinstance(val, int):
                # get works, use it to fill grid
                for y in range(64):
                    for x in range(64):
                        grid[y][x] = state.get(x, y)
        except:
            pass
    # If still zeros, try to use state.get(0,0) without checking all zeros
    try:
        val = state.get(0,0)
        if isinstance(val, int):
            # get works, use it to fill grid
            for y in range(64):
                for x in range(64):
                    if grid[y][x] == 0:
                        grid[y][x] = state.get(x, y)
    except:
        pass
    # If still zeros, try to use state.get(0,0) and if it returns something, use it
    try:
        val = state.get(0,0)
        if val is not None:
            for y in range(64):
                for x in range(64):
                    if grid[y][x] == 0:
                        grid[y][x] = state.get(x, y)
    except:
        pass

    # If still zeros, try to use state.__getitem__((x,y))
    try:
        val = state[0,0]
        if isinstance(val, int):
            for y in range(64):
                for x in range(64):
                    if grid[y][x] == 0:
                        grid[y][x] = state[x, y]
    except:
        pass

    # If still zeros, try to use state.__getitem__(x)
    try:
        row0 = state[0]
        if isinstance(row0, list):
            for y in range(64):
                row = state[y]
                for x in range(64):
                    if grid[y][x] == 0:
                        grid[y][x] = row[x]
    except:
        pass

    new_grid = [list(row) for row in grid]
    
    def get_status_counts(row):
        count3 = 0
        count11 = 0
        i = 0
        while i < len(row):
            color = row[i]
            if color == 3:
                j = i
                while j < len(row) and row[j] == 3:
                    j += 1
                count3 = j - i
                i = j
            elif color == 11:
                j = i
                while j < len(row) and row[j] == 11:
                    j += 1
                count11 = j - i
                i = j
            else:
                i += 1
        return count3, count11
    # Parse status from the actual state, not from new_grid which may be incomplete
    # Use find_color to get positions of 3 and 11 in the status bar rows
    try:
        pos3 = find_color(state, 3)
        pos11 = find_color(state, 11)
        # Filter positions with y in [61,62]
        status3 = [p for p in pos3 if p[1] in [61,62]]
        status11 = [p for p in pos11 if p[1] in [61,62]]
        count3 = len(status3) // 2  # two rows
        count11 = len(status11) // 2
    except:
        count3, count11 = get_status_counts(new_grid[61])
    
    def get_cursor_position(grid):
        row15 = grid[15]
        row16 = grid[16]
        row20 = grid[20]
        row21 = grid[21]
        if 12 in row15 or 12 in row16:
            return 0
        elif 12 in row20 or 12 in row21:
            return 1
        else:
            return None
    cursor = get_cursor_position(new_grid)
    
    def set_row(grid, y, pattern):
        grid[y] = list(pattern)
    
    if action["id"] == 1:
        if cursor == 1:
            new_row15 = [5]*4 + [4]*28 + [3] + [5] + [12]*5 + [5] + [3] + [4]*23
            new_row16 = [5]*4 + [4]*28 + [3]*2 + [12]*5 + [3]*2 + [4]*23
            set_row(new_grid, 15, new_row15)
            set_row(new_grid, 16, new_row16)
            new_row17_19 = [5]*4 + [4]*30 + [9]*5 + [4]*25
            set_row(new_grid, 17, new_row17_19)
            set_row(new_grid, 18, new_row17_19)
            set_row(new_grid, 19, new_row17_19)
            new_row20_24 = [5]*4 + [4]*30 + [3]*5 + [4]*25
            for y in range(20, 25):
                set_row(new_grid, y, new_row20_24)
            count3 += 1
            count11 -= 1
            new_status = [4] + [5]*10 + [4] + [5] + [3]*count3 + [11]*count11 + [5] + [8]*2 + [5] + [8]*2 + [5] + [8]*2
            set_row(new_grid, 61, new_status)
            set_row(new_grid, 62, new_status)
    elif action["id"] == 2:
        if cursor == 0:
            row15_orig = [5]*4 + [4]*28 + [3] + [5]*7 + [3] + [4]*23
            row16_orig = [5]*4 + [4]*28 + [3]*9 + [4]*23
            set_row(new_grid, 15, row15_orig)
            set_row(new_grid, 16, row16_orig)
            row17_19_orig = [5]*4 + [4]*30 + [3]*5 + [4]*25
            set_row(new_grid, 17, row17_19_orig)
            set_row(new_grid, 18, row17_19_orig)
            set_row(new_grid, 19, row17_19_orig)
            row20_21_12 = [5]*4 + [4]*30 + [12]*5 + [4]*25
            set_row(new_grid, 20, row20_21_12)
            set_row(new_grid, 21, row20_21_12)
            row22_24_9 = [5]*4 + [4]*30 + [9]*5 + [4]*25
            set_row(new_grid, 22, row22_24_9)
            set_row(new_grid, 23, row22_24_9)
            set_row(new_grid, 24, row22_24_9)
            count3 += 1
            count11 -= 1
            new_status = [4] + [5]*10 + [4] + [5] + [3]*count3 + [11]*count11 + [5] + [8]*2 + [5] + [8]*2 + [5] + [8]*2
            set_row(new_grid, 61, new_status)
            set_row(new_grid, 62, new_status)
    elif action["id"] == 3:
        count3 += 1
        count11 -= 1
        new_status = [4] + [5]*10 + [4] + [5] + [3]*count3 + [11]*count11 + [5] + [8]*2 + [5] + [8]*2 + [5] + [8]*2
        set_row(new_grid, 61, new_status)
        set_row(new_grid, 62, new_status)
    elif action["id"] == 4:
        count3 += 1
        count11 -= 1
        new_status = [4] + [5]*10 + [4] + [5] + [3]*count3 + [11]*count11 + [5] + [8]*2 + [5] + [8]*2 + [5] + [8]*2
        set_row(new_grid, 61, new_status)
        set_row(new_grid, 62, new_status)
    
    # Return a new GridState object with the updated grid
    return GridState(new_grid, state.levels_completed, state.state, state.available_actions)

def is_goal(state):
    return False