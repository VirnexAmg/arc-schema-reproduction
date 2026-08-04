# Tile-motion, transform-switch, and stopping-pad model grounded by transitions 1-14.
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


def _flip_sparse_panel_rows(grid):
    # Reflect the unique sparse row-pair in a bounded 10-wide 5/9 panel.
    for row in grid:
        for x0 in range(len(row) - 9):
            segment = row[x0:x0 + 10]
            bounded = (
                (x0 == 0 or row[x0 - 1] not in (5, 9))
                and (x0 + 10 == len(row) or row[x0 + 10] not in (5, 9))
            )
            if bounded and all(value in (5, 9) for value in segment) and segment.count(9) == 2:
                row[x0:x0 + 10] = list(reversed(segment))


def _move_token(grid, dy, dx, underlay):
    origin = _token_origin(grid)
    if origin is None:
        return False, underlay, False
    y0, x0 = origin
    y1, x1 = y0 + dy, x0 + dx
    size = 5
    if y1 < 0 or x1 < 0 or y1 + size > len(grid) or x1 + size > len(grid[0]):
        return False, underlay, False

    framed_interior = _framed_destination(grid, y1, x1)
    destination_values = [
        grid[y][x]
        for y in range(y1, y1 + size)
        for x in range(x1, x1 + size)
    ]
    ordinary_floor = all(value == 3 for value in destination_values)
    portal_entry = dy < 0 and not framed_interior and any(
        value == 5 for value in destination_values
    )
    marker_entry = (
        any(value in (0, 1) for value in destination_values)
        and all(value in (0, 1, 3) for value in destination_values)
    )
    if not ordinary_floor and not portal_entry and not marker_entry:
        return False, underlay, False

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
    if marker_entry:
        _flip_sparse_panel_rows(grid)
    return True, next_underlay, marker_entry


def _consume_meter(grid):
    for row in grid:
        for x, value in enumerate(row):
            if value == 11:
                row[x] = 3
                break


def init_state(entry_grid):
    return {
        "actions": [],
        "underlay": [[3 for x in range(5)] for y in range(5)],
        "transform_parity": False,
    }


def predict(latent, grid, action):
    action_id = int(action["id"])
    nxt = deepcopy(grid)
    moved = False
    marker_entry = False
    underlay = latent.get("underlay")
    if action_id == 1:
        moved, underlay, marker_entry = _move_token(nxt, -5, 0, underlay)
    elif action_id == 2:
        moved, underlay, marker_entry = _move_token(nxt, 5, 0, underlay)
    elif action_id == 3:
        moved, underlay, marker_entry = _move_token(nxt, 0, -5, underlay)
    elif action_id == 4:
        moved, underlay, marker_entry = _move_token(nxt, 0, 5, underlay)
    if moved and not marker_entry:
        _consume_meter(nxt)
    transform_parity = latent.get("transform_parity", False)
    if marker_entry:
        transform_parity = not transform_parity
    nxt_latent = {
        "actions": latent["actions"] + [action_id],
        "underlay": underlay,
        "transform_parity": transform_parity,
    }
    return nxt, [], nxt_latent


def is_goal(latent, grid):
    underlay = latent.get("underlay")
    on_upper_pad = underlay is not None and any(
        value == 5 for row in underlay for value in row
    )
    return bool(latent.get("transform_parity", False) and on_upper_pad)
