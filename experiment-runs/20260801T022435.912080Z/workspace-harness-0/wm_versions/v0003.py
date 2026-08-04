# Tile-motion model grounded by transition 1.
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


def _move_token(grid, dy, dx):
    origin = _token_origin(grid)
    if origin is None:
        return
    y0, x0 = origin
    y1, x1 = y0 + dy, x0 + dx
    size = 5
    if y1 < 0 or x1 < 0 or y1 + size > len(grid) or x1 + size > len(grid[0]):
        return
    for y in range(y1, y1 + size):
        for x in range(x1, x1 + size):
            if grid[y][x] != 3:
                return
    sprite = []
    for y in range(y0, y0 + size):
        sprite.append(grid[y][x0:x0 + size])
    for y in range(y0, y0 + size):
        for x in range(x0, x0 + size):
            grid[y][x] = 3
    for sy in range(size):
        for sx in range(size):
            grid[y1 + sy][x1 + sx] = sprite[sy][sx]


def _consume_meter(grid):
    # Each observed action consumes the leftmost column of every color-11 row.
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
    if action_id == 1:
        _move_token(nxt, -5, 0)
    _consume_meter(nxt)
    nxt_latent = {"actions": latent["actions"] + [action_id]}
    return nxt, [], nxt_latent


def is_goal(latent, grid):
    return False
