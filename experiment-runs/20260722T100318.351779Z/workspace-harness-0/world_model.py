# Tile-based maze model inferred from the recorded transitions.
# Helpers available: GridState, find_color, bbox, neighbors4, deepcopy


def _player_pos(frame):
    # The movable object is a 5x5 block whose upper two rows are color 12
    # and whose lower three rows are color 9. Restrict the search to the maze.
    for y in range(0, 57):
        for x in range(0, 60):
            good = True
            for dy in range(5):
                expected = 12 if dy < 2 else 9
                for dx in range(5):
                    if frame[y + dy][x + dx] != expected:
                        good = False
                        break
                if not good:
                    break
            if good:
                return (x, y)
    return None


def _draw_player(frame, x, y):
    for dy in range(5):
        color = 12 if dy < 2 else 9
        for dx in range(5):
            frame[y + dy][x + dx] = color


def _advance_bar(frame, level):
    # Every recorded action, including a blocked movement, advances this bar.
    progress = 0
    while 13 + progress < 55 and frame[61][13 + progress] == 3:
        progress += 1
    if progress < 42:
        # Countdown speed increases with completed-level count: observed first
        # board advances one column per action and the second advances two.
        progress += level + 1
        if progress > 42:
            progress = 42
    for y in (61, 62):
        for x in range(13, 55):
            frame[y][x] = 3 if x < 13 + progress else 11


def _decode_row(spec):
    row = []
    for part in spec.split(","):
        color, count = part.split(":")
        row += [int(color)] * int(count)
    return row


def _load_second_level(nxt):
    # The level transition deterministically installs this board.  Rows are
    # grounded directly by the observed transition rather than synthesized by
    # moving the old level's objects.
    blocks = [
        (0, 4, "5:4,4:60"),
        (5, 9, "5:4,4:15,3:35,4:10"),
        (10, 14, "5:4,4:5,3:45,4:10"),
        (15, 15, "5:4,4:5,3:15,4:5,3:10,4:5,3:10,4:10"),
        (16, 16, "5:4,4:5,3:6,11:3,3:6,4:5,3:10,4:5,3:10,4:10"),
        (17, 17, "5:4,4:5,3:6,11:1,3:1,11:1,3:6,4:5,3:10,4:5,3:10,4:10"),
        (18, 18, "5:4,4:5,3:6,11:3,3:6,4:5,3:10,4:5,3:10,4:10"),
        (19, 19, "5:4,4:5,3:15,4:5,3:10,4:5,3:10,4:10"),
        (20, 24, "5:4,4:5,3:15,4:5,3:10,4:10,3:10,4:5"),
        (25, 29, "5:4,4:10,3:5,4:15,3:10,4:5,3:10,4:5"),
        (30, 34, "5:4,4:10,3:5,4:15,3:10,4:5,3:5,4:10"),
        (35, 37, "5:4,4:10,3:5,4:10,3:10,4:10,3:5,4:10"),
        (38, 38, "5:4,4:8,3:9,4:8,3:10,4:10,3:5,4:10"),
        (39, 39, "5:4,4:8,3:1,5:7,3:1,4:8,3:10,4:10,3:10,4:5"),
        (40, 40, "5:4,4:8,3:1,5:7,3:1,4:8,12:5,3:5,4:5,3:15,4:5"),
        (41, 41, "5:4,4:8,3:1,5:2,9:3,5:2,3:1,4:8,12:5,3:5,4:5,3:15,4:5"),
        (42, 42, "5:4,4:8,3:1,5:2,9:1,5:4,3:1,4:8,9:5,3:5,4:5,3:15,4:5"),
        (43, 43, "5:4,4:8,3:1,5:2,9:1,5:1,9:1,5:2,3:1,4:8,9:5,3:5,4:5,3:15,4:5"),
        (44, 44, "5:4,4:8,3:1,5:7,3:1,4:8,9:5,3:5,4:5,3:15,4:5"),
        (45, 45, "5:4,4:8,3:1,5:7,3:1,4:23,3:15,4:5"),
        (46, 46, "5:4,4:8,3:9,4:23,3:7,0:1,3:7,4:5"),
        (47, 47, "5:4,4:40,3:6,1:1,0:2,3:6,4:5"),
        (48, 48, "5:4,4:40,3:7,1:1,3:7,4:5"),
        (49, 49, "5:4,4:40,3:15,4:5"),
        (50, 50, "5:4,4:35,3:20,4:5"),
        (51, 51, "5:4,4:35,3:1,11:3,3:16,4:5"),
        (52, 52, "4:39,3:1,11:1,3:1,11:1,3:16,4:5"),
        (53, 53, "4:1,5:10,4:28,3:1,11:3,3:16,4:5"),
        (54, 54, "4:1,5:10,4:28,3:20,4:5"),
        (55, 56, "4:1,5:2,9:6,5:2,4:53"),
        (57, 58, "4:1,5:6,9:2,5:2,4:53"),
        (59, 59, "4:1,5:2,9:2,5:2,9:2,5:2,4:53"),
        (60, 60, "4:1,5:2,9:2,5:2,9:2,5:2,4:1,5:52"),
        (61, 62, "4:1,5:10,4:1,5:1,11:42,5:1,8:2,5:1,8:2,5:1,8:2"),
        (63, 63, "4:12,5:52")
    ]
    for y0, y1, spec in blocks:
        row = _decode_row(spec)
        for y in range(y0, y1 + 1):
            nxt.frame[y] = row[:]
    nxt.levels_completed = 1


def step(state, action):
    nxt = state.copy()
    aid = int(action["id"])

    # Entering the upper chamber completed the first level and replaced the
    # entire maze on the recorded action.
    old_pos = _player_pos(state.frame)
    if state.levels_completed == 0 and old_pos == (34, 15) and aid == 1:
        _load_second_level(nxt)
        return nxt

    # Once the countdown is already full, the following action restarts the
    # current board at its initial position and consumes the rightmost life.
    # The final recorded transition on level two exhibits this reset rather
    # than carrying out the requested downward movement.
    if state.levels_completed == 1:
        timer_full = True
        for xx in range(13, 55):
            if state.frame[61][xx] != 3:
                timer_full = False
                break
        if timer_full:
            lives = 0
            for xx in (56, 59, 62):
                if state.frame[61][xx] == 8:
                    lives += 1
            _load_second_level(nxt)
            remaining = lives - 1
            for i, xx in enumerate((56, 59, 62)):
                if i >= remaining:
                    for yy in (61, 62):
                        nxt.frame[yy][xx] = 3
                        nxt.frame[yy][xx + 1] = 3
            return nxt

    # Entering the lower-right 0/1 glyph from above consumes it and places the
    # player on the adjacent tile to its right.  This transition also changes
    # the inventory display and extends its background across the bottom row.
    if state.levels_completed == 1 and old_pos == (49, 40) and aid == 2:
        for yy in range(40, 50):
            for xx in range(44, 54):
                nxt.frame[yy][xx] = 3
        _draw_player(nxt.frame, 49, 45)
        inventory = {
            55: "4:1,5:2,9:2,5:2,9:2,5:2,4:53",
            56: "4:1,5:2,9:2,5:2,9:2,5:2,4:53",
            59: "4:1,5:2,9:6,5:2,4:53",
            60: "4:1,5:2,9:6,5:2,4:1,5:52"
        }
        for yy, spec in inventory.items():
            nxt.frame[yy] = _decode_row(spec)
        _advance_bar(nxt.frame, state.levels_completed)
        return nxt

    # From the observations: ACTION1 moves one tile upward, ACTION2 moves one
    # tile downward, and ACTION3 attempts the leftward move (which was blocked
    # by the wall at x=29..33). ACTION4 is the remaining horizontal direction.
    moves = {
        1: (0, -5),
        2: (0, 5),
        3: (-5, 0),
        4: (5, 0)
    }

    pos = _player_pos(state.frame)
    if pos is not None and aid in moves:
        x, y = pos
        dx, dy = moves[aid]
        nx, ny = x + dx, y + dy

        can_move = nx >= 0 and ny >= 0 and nx + 4 < 64 and ny + 4 < 61
        if can_move:
            # Color 4 is the maze wall. Colors 0 and 1 form the destination
            # marker and are traversable, as is ordinary color-3 floor.
            for yy in range(ny, ny + 5):
                for xx in range(nx, nx + 5):
                    if state.frame[yy][xx] == 4:
                        can_move = False
                        break
                if not can_move:
                    break

        collected = False
        if can_move:
            # The small 0/1 glyph is a collectible.  Entering its tile consumes
            # it, changes the matching inventory glyph below the maze, and does
            # not advance the countdown on that particular turn.
            collected_key = False
            collected_goal = False
            for yy in range(ny, ny + 5):
                for xx in range(nx, nx + 5):
                    cell = state.frame[yy][xx]
                    if cell == 0 or cell == 1:
                        collected_key = True
                    elif cell == 11:
                        collected_goal = True
            collected = collected_key or collected_goal
            for yy in range(y, y + 5):
                for xx in range(x, x + 5):
                    nxt.frame[yy][xx] = 3
            # The floor glyph at (19,30) is persistent: it is hidden while
            # occupied and reappears when the player leaves.  Touching it
            # still updates the corresponding status icon below.
            if x == 19 and y == 30:
                nxt.frame[31][21] = 0
                nxt.frame[32][20] = 1
                nxt.frame[32][21] = 0
                nxt.frame[32][22] = 0
                nxt.frame[33][21] = 1
            # Likewise, the lower-right 0/1 glyph is a persistent floor
            # marking. It is hidden by the player at tile (49,45) and must be
            # restored when that tile is vacated.
            if x == 49 and y == 45:
                nxt.frame[46][51] = 0
                nxt.frame[47][50] = 1
                nxt.frame[47][51] = 0
                nxt.frame[47][52] = 0
                nxt.frame[48][51] = 1
            _draw_player(nxt.frame, nx, ny)
            if collected_goal:
                for yy in (61, 62):
                    for xx in range(13, 55):
                        nxt.frame[yy][xx] = 11
            if collected:
                for yy in (57, 58):
                    for xx in range(1, 11):
                        nxt.frame[yy][xx] = 5
                    nxt.frame[yy][7] = 9
                    nxt.frame[yy][8] = 9

    if aid in moves and not (pos is not None and can_move and collected):
        _advance_bar(nxt.frame, state.levels_completed)
    return nxt


def _inside_exit_frame(frame, x, y):
    # In the observed exit chamber the player is surrounded by one column of
    # color 5, with the outer color-3 rails six cells from its left edge.
    if x < 6 or x + 6 >= 64:
        return False
    left = True
    right = True
    for yy in range(y, y + 5):
        left = left and frame[yy][x - 6] == 3
        right = right and frame[yy][x + 6] == 3
    return left and right


def _has_key_marker(frame):
    # The level's 0/1 key glyph occupies the lower-right chamber.  It is
    # overwritten by the player when collected and does not reappear.
    for y in range(45, 50):
        for x in range(44, 49):
            if frame[y][x] == 0 or frame[y][x] == 1:
                return True
    return False


def is_goal(state):
    if state.state == "WIN":
        return True
    pos = _player_pos(state.frame)
    # As on the completed first board, entering the chamber containing the
    # 11-colored glyph is the level objective.  The remote 0/1 glyph is a
    # collectible rather than a prerequisite for this chamber.
    # The 11 glyph at the current chamber is a timer-reset collectible, not
    # the level exit.  Seek the remaining 0/1 objective in the lower-right
    # chamber; its 3x3 glyph is covered from tile position (44,45).
    # The lower 11-glyph at (39,50) only reset the countdown and did not
    # complete the level.  The remaining matching chamber is at (14,15);
    # use it as the next grounded subgoal while its transition is unobserved.
    # A coordinate alone is not sufficient: the player has now reached
    # (14,15) without completing the level.  Only an observed level advance
    # or terminal state certifies success.
    return state.state == "WIN" or state.levels_completed > 1
