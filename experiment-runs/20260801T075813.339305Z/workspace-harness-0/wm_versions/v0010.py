# Object-level model grounded by observed transitions across levels.


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
    # The timer occupies the two rows immediately above the bottom border.
    # In the first level an ordinary action consumed one cell per row; in the
    # current cyan-source level it consumes two. The separate upper cyan glyph
    # provides a visible entry-grid cue for the larger rate.
    h = len(grid)
    rate = 1
    for r in range(max(0, h - 3)):
        for c in range(len(grid[r])):
            if grid[r][c] == 11:
                rate = 2
    for r in range(max(0, h - 3), h):
        cyan = []
        for c in range(len(grid[r])):
            if grid[r][c] == 11:
                cyan.append(c)
        for i in range(rate):
            if i < len(cyan):
                grid[r][cyan[i]] = 3


def _sync_large_glyph(grid):
    # A small upper glyph is copied at 2x scale into the lower-left display.
    upper = []
    lower = []
    h = len(grid)
    for r in range(h):
        for c in range(len(grid[r])):
            if grid[r][c] == 9:
                if r < h // 3:
                    upper.append((r, c))
                elif r > (3 * h) // 4 and c < len(grid[r]) // 3:
                    lower.append((r, c))
    # Later levels may render the small source glyph in cyan rather than red.
    if not upper:
        for r in range(h // 3):
            for c in range(len(grid[r])):
                if grid[r][c] == 11:
                    upper.append((r, c))
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


def _exit_target(grid):
    # Exit panels are compact 7x7 gray frames. Return the top-left coordinate
    # of the 5x5 interior without assuming a level-specific panel position.
    h = len(grid)
    w = len(grid[0]) if h else 0
    seen = set()
    for sr in range(h):
        for sc in range(w):
            if grid[sr][sc] != 5 or (sr, sc) in seen:
                continue
            stack = [(sr, sc)]
            comp = []
            seen.add((sr, sc))
            while stack:
                r, c = stack.pop()
                comp.append((r, c))
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < h and 0 <= cc < w:
                        if grid[rr][cc] == 5 and (rr, cc) not in seen:
                            seen.add((rr, cc))
                            stack.append((rr, cc))
            r0 = min(p[0] for p in comp)
            r1 = max(p[0] for p in comp)
            c0 = min(p[1] for p in comp)
            c1 = max(p[1] for p in comp)
            if r1 - r0 == 6 and c1 - c0 == 6 and len(comp) >= 20:
                return (r0 + 1, c0 + 1)
    return None


def init_state(entry_grid):
    return {
        "moves": {1: (-5, 0), 2: (5, 0), 3: (0, -5), 4: (0, 5)},
        "actions": 0,
        "synced": False,
        "complete": False,
        "under": [],
        "target": _exit_target(entry_grid),
    }


def predict(latent, grid, action):
    nxt = deepcopy(grid)
    out = deepcopy(latent)
    aid = int(action["id"])
    delta = out["moves"].get(aid)
    box = _purple_tile(grid)
    touched_motif = False
    moved = False
    if delta is not None and box is not None:
        r0, c0, r1, c1 = box
        dr, dc = delta
        nr0 = r0 + dr
        nc0 = c0 + dc
        in_bounds = nr0 >= 0 and nc0 >= 0
        in_bounds = in_bounds and nr0 + 4 < len(grid) and nc0 + 4 < len(grid[0])
        floor_legal = in_bounds
        entered_panel = False
        target = out.get("target")
        if in_bounds:
            for r in range(nr0, nr0 + 5):
                for c in range(nc0, nc0 + 5):
                    color = grid[r][c]
                    in_panel = out.get("synced") and color in (5, 9)
                    if color in (0, 1):
                        touched_motif = True
                    elif color != 3 and not in_panel:
                        floor_legal = False
                    if in_panel:
                        entered_panel = True
        # Completion occurs when the synchronized tile exactly fills the 5x5
        # interior of the compact gray exit frame.
        if entered_panel and target is not None and (nr0, nc0) == target:
            out["actions"] += 1
            out["complete"] = True
            return nxt, ["LEVEL_COMPLETE"], out
        if floor_legal:
            tile = []
            for r in range(r0, r1 + 1):
                tile.append(grid[r][c0:c1 + 1])
            underlying = {}
            for item in out.get("under", []):
                underlying[(item[0], item[1])] = item[2]
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    nxt[r][c] = underlying.get((r, c), 3)
            new_under = []
            for r in range(nr0, nr0 + 5):
                for c in range(nc0, nc0 + 5):
                    new_under.append((r, c, grid[r][c]))
            for rr in range(5):
                for cc in range(5):
                    nxt[nr0 + rr][nc0 + cc] = tile[rr][cc]
            out["under"] = new_under
            moved = True
            if touched_motif:
                _sync_large_glyph(nxt)
                out["synced"] = True
    # Ordinary moves and blocked attempts consume timer; motif activation does not.
    if not (moved and touched_motif):
        _advance_bar(nxt)
    out["actions"] += 1
    return nxt, [], out


def is_goal(latent, grid):
    return bool(latent.get("complete"))
