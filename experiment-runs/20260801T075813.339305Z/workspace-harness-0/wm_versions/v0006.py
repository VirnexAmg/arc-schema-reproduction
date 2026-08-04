# Object-level model grounded by the first four transitions.
# The movable 5x5 purple/red tile has four confirmed cardinal actions; the black/blue motif is static so far.


def _purple_tile(grid):
    cells = []
    for r in range(len(grid)):
        for c in range(len(grid[r])):
            if grid[r][c] == 12:
                cells.append((r, c))
    if not cells:
        return None
    r0 = min(p[0] for p in cells)
    c0 = min(p[1] for p in cells)
    return (r0, c0, r0 + 4, c0 + 4)


def _advance_bar(grid):
    # Each observed action consumes the leftmost cyan cell in both status-bar rows.
    for r in range(len(grid)):
        cyan = []
        for c in range(len(grid[r])):
            if grid[r][c] == 11:
                cyan.append(c)
        if cyan:
            grid[r][cyan[0]] = 3


def init_state(entry_grid):
    return {
        "moves": {1: (-5, 0), 2: (5, 0), 3: (0, -5), 4: (0, 5)},
        "actions": 0,
    }


def predict(latent, grid, action):
    nxt = deepcopy(grid)
    out = deepcopy(latent)
    aid = int(action["id"])
    delta = out["moves"].get(aid)
    box = _purple_tile(grid)
    if delta is not None and box is not None:
        r0, c0, r1, c1 = box
        dr, dc = delta
        nr0 = r0 + dr
        nc0 = c0 + dc
        legal = nr0 >= 0 and nc0 >= 0
        legal = legal and nr0 + 4 < len(grid) and nc0 + 4 < len(grid[0])
        if legal:
            for r in range(nr0, nr0 + 5):
                for c in range(nc0, nc0 + 5):
                    if grid[r][c] != 3:
                        legal = False
        if legal:
            tile = []
            for r in range(r0, r1 + 1):
                tile.append(grid[r][c0:c1 + 1])
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    nxt[r][c] = 3
            for rr in range(5):
                for cc in range(5):
                    nxt[nr0 + rr][nc0 + cc] = tile[rr][cc]
    _advance_bar(nxt)
    out["actions"] += 1
    return nxt, [], out


def is_goal(latent, grid):
    return False
