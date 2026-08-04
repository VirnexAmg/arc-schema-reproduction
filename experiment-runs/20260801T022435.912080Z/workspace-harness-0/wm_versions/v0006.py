# Tile-motion and stopping-pad model grounded by transitions 1-9.
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
    if y0 < 1 or x0 < 1 or y0 + 5 >= len(grid) or x0 + 5 >= len(grid[0]):
        return False
    cap = all(grid[y0 - 1][x] == 5 for x in range(x0, x0 + 5))
    rails = all(
        grid[y][x0 - 1] == 5 and grid[y][x0 + 5] == 5
        for y in range(y0, y0 + 5)
    )
    return cap and rails


def _move_token(grid, dy, dx, underlay):
    origin = _token_origin(grid)
    if origin is None:
        return False, underlay
    y0, x0 = origin
    y1, x1 = y0 + dy, x0 + dx
    size = 5
    if y1 < 0 or x1 < 0 or y1 + size > len(grid) or x1 + size > len(grid[0]):
        return False, underlay

    framed_interior = _framed_destination(grid, y1, x1)
    ordinary_floor = all(
        grid[y][x] == 3
        for y in range(y1, y1 + size)
        for x in range(x1, x1 + size)
    )
    # Transition 8 permits upward entry into the lower color-5 portal band.
    # Transition 9 shows that the framed interior immediately above is blocked.
    portal_entry = dy < 0 and not framed_interior and any(
        grid[y][x] == 5
        for y in range(y1, y1 + size)
        for x in range(x1, x1 + size)
    )
    if not ordinary_floor and not portal_entry:
        return False, underlay

    sprite = [grid[y][x0:x0 + size] for y in range(y0, y0 + size)]
    next_underlay = [grid[y][x1:x1 + size] for y in range(y1, y1 + size)]
    for sy in range(size):
        for sx in range(size):
            if underlay is None:
                grid[y0 + sy][x0 + sx] = 3
            else:
                grid[y0 + sy][x0 + sx] = underlay[sy][sx]
    for sy in range(size):
        for sx in range(size):
            grid[y1 + sy][x1 + sx] = sprite[sy][sx]
    return True, next_underlay


def _consume_meter(grid):
    for row in grid:
        for x, value in enumerate(row):
            if value == 11:
                row[x] = 3
                break


def init_state(entry_grid):
    return {"actions": [], "underlay": [[3 for x in range(5)] for y in range(5)]}


def predict(latent, grid, action):
    action_id = int(action["id"])
    nxt = deepcopy(grid)
    moved = False
    underlay = latent.get("underlay")
    if action_id == 1:
        moved, underlay = _move_token(nxt, -5, 0, underlay)
    elif action_id == 2:
        moved, underlay = _move_token(nxt, 5, 0, underlay)
    if moved:
        _consume_meter(nxt)
    nxt_latent = {
        "actions": latent["actions"] + [action_id],
        "underlay": underlay,
    }
    return nxt, [], nxt_latent


def is_goal(latent, grid):
    return False
