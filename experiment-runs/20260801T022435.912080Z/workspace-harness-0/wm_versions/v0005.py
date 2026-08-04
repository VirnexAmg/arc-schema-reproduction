# Tile-motion and framed-portal model grounded by transitions 1-8.
# The movable token is the 5x5 component whose top rows contain color 12.

def _token_origin(grid):
    points = []
    for y, row in enumerate(grid):
        for x, value in enumerate(row):
            if value == 12:
                points.append((y, x))
    if not points:
        return None
    return min(y for y, x in points), min(x for y, x in points)


def _framed_destination(grid, y0, x0):
    # A five-cell interior with a color-5 cap and side rails is a goal frame.
    if y0 < 1 or x0 < 1 or y0 + 5 >= len(grid) or x0 + 5 >= len(grid[0]):
        return False
    cap = all(grid[y0 - 1][x] == 5 for x in range(x0, x0 + 5))
    rails = all(
        grid[y][x0 - 1] == 5 and grid[y][x0 + 5] == 5
        for y in range(y0, y0 + 5)
    )
    return cap and rails


def _move_token(grid, dy, dx):
    origin = _token_origin(grid)
    if origin is None:
        return False
    y0, x0 = origin
    y1, x1 = y0 + dy, x0 + dx
    size = 5
    if y1 < 0 or x1 < 0 or y1 + size > len(grid) or x1 + size > len(grid[0]):
        return False

    reached_frame = _framed_destination(grid, y1, x1)
    ordinary_floor = all(
        grid[y][x] == 3
        for y in range(y1, y1 + size)
        for x in range(x1, x1 + size)
    )
    # Transition 8 shows that an upward move may enter a color-5 portal band
    # even when the footprint also crosses the surrounding wall color.
    portal_entry = dy < 0 and any(
        grid[y][x] == 5
        for y in range(y1, y1 + size)
        for x in range(x1, x1 + size)
    )
    if not ordinary_floor and not portal_entry:
        return False

    sprite = [grid[y][x0:x0 + size] for y in range(y0, y0 + size)]
    for y in range(y0, y0 + size):
        for x in range(x0, x0 + size):
            grid[y][x] = 3
    for sy in range(size):
        for sx in range(size):
            grid[y1 + sy][x1 + sx] = sprite[sy][sx]
    return reached_frame


def _consume_meter(grid):
    # Every observed action consumes the leftmost color-11 column in each row.
    for row in grid:
        for x, value in enumerate(row):
            if value == 11:
                row[x] = 3
                break


def init_state(entry_grid):
    return {"actions": []}


def predict(latent, grid, action):
    action_id = int(action["id"])
    nxt = deepcopy(grid)
    reached_frame = False
    if action_id == 1:
        reached_frame = _move_token(nxt, -5, 0)
    elif action_id == 2:
        reached_frame = _move_token(nxt, 5, 0)
    _consume_meter(nxt)
    nxt_latent = {"actions": latent["actions"] + [action_id]}
    events = ["LEVEL_COMPLETE"] if reached_frame else []
    return nxt, events, nxt_latent


def is_goal(latent, grid):
    origin = _token_origin(grid)
    return origin is not None and _framed_destination(grid, origin[0], origin[1])
