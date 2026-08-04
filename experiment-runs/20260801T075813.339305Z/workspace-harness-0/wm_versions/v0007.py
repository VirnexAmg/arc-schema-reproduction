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


def _sync_large_glyph(grid):
    # The small upper panel is a 1x target glyph; the lower-left panel is its 2x display.
    upper = []
    lower = []
    h = len(grid)
    for r in range(h):
        for c in range(len(grid[r])):
            if grid[r][c] == 9:
                if r < h // 3:
                    upper.append((r, c))
                elif r > (3 * h) // 4:
                    lower.append((r, c))
    if not upper or not lower:
        return
    ur0 = min(p[0] for p in upper)
    uc0 = min(p[1] for p in upper)
    lr0 = min(p[0] for p in lower)
    lc0 = min(p[1] for p in lower)
    for r, c in lower:
        grid[r][c] = 5
    for r, c in upper:
        rr0 = lr0 + 2 * (r - ur0)
        cc0 = lc0 + 2 * (c - uc0)
        for rr in range(rr0, rr0 + 2):
            for cc in range(cc0, cc0 + 2):
                grid[rr][cc] = 9


def init_state(entry_grid):
    return {
        "moves": {1: (-5, 0), 2: (5, 0), 3: (0, -5), 4: (0, 5)},
        "actions": 0,
        "synced": False,
        "complete": False,
    }


def predict(latent, grid, action):
    nxt = deepcopy(grid)
    out = deepcopy(latent)
    aid = int(action["id"])
    delta = out["moves"].get(aid)
    box = _purple_tile(grid)
    consumed_motif = False
    moved = False
    if delta is not None and box is not None:
        r0, c0, r1, c1 = box
        dr, dc = delta
        nr0 = r0 + dr
        nc0 = c0 + dc
        in_bounds = nr0 >= 0 and nc0 >= 0
        in_bounds = in_bounds and nr0 + 4 < len(grid) and nc0 + 4 < len(grid[0])
        floor_legal = in_bounds
        target_contact = False
        if in_bounds:
            for r in range(nr0, nr0 + 5):
                for c in range(nc0, nc0 + 5):
                    color = grid[r][c]
                    if color in (0, 1):
                        consumed_motif = True
                    elif color != 3:
                        floor_legal = False
                    if out.get("synced") and nr0 < len(grid) // 3 and color in (5, 9):
                        target_contact = True
        if target_contact:
            out["actions"] += 1
            out["complete"] = True
            return nxt, ["LEVEL_COMPLETE"], out
        if floor_legal:
            tile = []
            for r in range(r0, r1 + 1):
                tile.append(grid[r][c0:c1 + 1])
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    nxt[r][c] = 3
            for rr in range(5):
                for cc in range(5):
                    nxt[nr0 + rr][nc0 + cc] = tile[rr][cc]
            moved = True
            if consumed_motif:
                _sync_large_glyph(nxt)
                out["synced"] = True
    # Ordinary moves and blocked attempts consume timer; successful motif contact does not.
    if not (moved and consumed_motif):
        _advance_bar(nxt)
    out["actions"] += 1
    return nxt, [], out


def is_goal(latent, grid):
    return bool(latent.get("complete"))
