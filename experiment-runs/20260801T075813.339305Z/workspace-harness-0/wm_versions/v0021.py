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


def _timer_rate(grid):
    # The current level exposes a separate upper cyan glyph and consumes two
    # timer cells per action; the earlier level without it consumed one.
    h = len(grid)
    for r in range(max(0, h - 3)):
        for c in range(len(grid[r])):
            if grid[r][c] == 11:
                return 2
    return 1


def _advance_bar(grid, rate):
    h = len(grid)
    for r in range(max(0, h - 3), h):
        cyan = []
        for c in range(len(grid[r])):
            if grid[r][c] == 11:
                cyan.append(c)
        for i in range(rate):
            if i < len(cyan):
                grid[r][cyan[i]] = 3


def _sync_large_glyph(grid):
    # Compatibility mechanism for the first level, where the observed switch
    # result exactly copied the small upper glyph at 2x scale.
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


def _transform_large(grid, kind):
    # Transform the doubled red glyph inside the lower-left display as one
    # object. Evidence 36 identifies the black/blue switch as a vertical flip.
    cells = []
    h = len(grid)
    for r in range(h):
        for c in range(len(grid[r])):
            if grid[r][c] == 9 and r > (3 * h) // 4 and c < len(grid[r]) // 3:
                cells.append((r, c))
    if not cells:
        return
    r0 = min(p[0] for p in cells)
    r1 = max(p[0] for p in cells)
    c0 = min(p[1] for p in cells)
    c1 = max(p[1] for p in cells)
    for r, c in cells:
        grid[r][c] = 5
    for r, c in cells:
        if kind == "vflip":
            rr = r1 - (r - r0)
            cc = c
        else:
            # The reset-state glyph differs from the exit only by reflection
            # across the vertical axis. The cyan operation is provisionally
            # grounded as that horizontal flip.
            rr = r
            cc = c1 - (c - c0)
        grid[rr][cc] = 9


def _exit_target(grid):
    # Exit panels are compact 7x7 gray frames with a 5x5 interior.
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


def _glyph_matches_exit(grid, target):
    if target is None:
        return False
    red = []
    h = len(grid)
    for r in range(h):
        for c in range(len(grid[r])):
            if grid[r][c] == 9 and r > (3 * h) // 4 and c < len(grid[r]) // 3:
                red.append((r, c))
    if not red:
        return False
    r0 = min(p[0] for p in red)
    c0 = min(p[1] for p in red)
    large = []
    small = []
    tr, tc = target
    for rr in range(3):
        for cc in range(3):
            filled = False
            for r in range(r0 + 2 * rr, r0 + 2 * rr + 2):
                for c in range(c0 + 2 * cc, c0 + 2 * cc + 2):
                    if grid[r][c] == 9:
                        filled = True
            large.append(filled)
            small.append(grid[tr + 1 + rr][tc + 1 + cc] == 9)
    # The current black switch produces the exit motif in actor-facing
    # orientation: the large display is a half-turn of the motif as shown in
    # the distant panel. Preserve exact matching for levels whose displays
    # share screen orientation, while admitting this object-level relation.
    return large == small or large == list(reversed(small))


def init_state(entry_grid):
    return {
        "moves": {1: (-5, 0), 2: (5, 0), 3: (0, -5), 4: (0, 5)},
        "actions": 0,
        "synced": False,
        "complete": False,
        "under": [],
        "target": _exit_target(entry_grid),
        "timer_rate": _timer_rate(entry_grid),
    }


def predict(latent, grid, action):
    nxt = deepcopy(grid)
    out = deepcopy(latent)
    aid = int(action["id"])
    delta = out["moves"].get(aid)
    box = _purple_tile(grid)
    touched_black = False
    touched_cyan = False
    moved = False
    rate = out.get("timer_rate", _timer_rate(grid))
    # Capture reusable entry-state objects on the first prediction. They ground
    # a delayed timeout reset without memorizing a trajectory.
    if "spawn" not in out:
        out["spawn"] = box
        out["timer_cells"] = []
        out["initial_cyan"] = []
        out["initial_red"] = []
        h = len(grid)
        w = len(grid[0]) if h else 0
        for r in range(h):
            for c in range(len(grid[r])):
                if r >= h - 3 and grid[r][c] == 11:
                    out["timer_cells"].append((r, c))
                elif grid[r][c] == 11:
                    # Recharge sources are attempt-local objects. A timeout
                    # reset restores their entry-state cyan ring cells.
                    out["initial_cyan"].append((r, c))
                if r > (3 * h) // 4 and c < w // 3 and grid[r][c] == 9:
                    out["initial_red"].append((r, c))

    # In the two-cell-rate level, empty is a visible intermediate state. The
    # following input is consumed by a soft timeout: refill the bar, spend the
    # rightmost reserve, restore the entry glyph, sources, and actor spawn.
    if rate == 2:
        timer_empty = True
        h = len(grid)
        for r in range(max(0, h - 3), h):
            for c in range(len(grid[r])):
                if grid[r][c] == 11:
                    timer_empty = False
        if timer_empty:
            # Each reserve occupies two columns across the two timer rows.
            # A nonfinal reserve funds a soft attempt reset; consuming the
            # final marker ends the life instead, leaving the outer harness to
            # begin a fresh episode from the unchanged level entry.
            reserve_cells = []
            reserve_cols = set()
            for r in range(max(0, h - 3), h):
                for c in range(len(grid[r])):
                    if grid[r][c] == 8:
                        reserve_cells.append((r, c))
                        reserve_cols.add(c)
            if len(reserve_cols) <= 2:
                for r, c in reserve_cells:
                    nxt[r][c] = 3
                out["actions"] += 1
                return nxt, ["GAME_OVER"], out
            if box is not None and out.get("spawn") is not None:
                r0, c0, r1, c1 = box
                tile = []
                for r in range(r0, r1 + 1):
                    tile.append(grid[r][c0:c1 + 1])
                underlying = {}
                for item in out.get("under", []):
                    underlying[(item[0], item[1])] = item[2]
                for r in range(r0, r1 + 1):
                    for c in range(c0, c1 + 1):
                        nxt[r][c] = underlying.get((r, c), 3)
                sr0, sc0, sr1, sc1 = out["spawn"]
                new_under = []
                for r in range(sr0, sr1 + 1):
                    for c in range(sc0, sc1 + 1):
                        new_under.append((r, c, nxt[r][c]))
                for rr in range(5):
                    for cc in range(5):
                        nxt[sr0 + rr][sc0 + cc] = tile[rr][cc]
                out["under"] = new_under
            w = len(nxt[0]) if h else 0
            for r in range(h):
                for c in range(w // 3):
                    if r > (3 * h) // 4 and nxt[r][c] == 9:
                        nxt[r][c] = 5
            for r, c in out.get("initial_red", []):
                nxt[r][c] = 9
            for r, c in out.get("initial_cyan", []):
                nxt[r][c] = 11
            for r, c in out.get("timer_cells", []):
                nxt[r][c] = 11
            reserves = []
            for r in range(max(0, h - 3), h):
                for c in range(len(nxt[r])):
                    if nxt[r][c] == 8:
                        reserves.append((r, c))
            if reserves:
                right = max(p[1] for p in reserves)
                for r, c in reserves:
                    if c >= right - 1:
                        nxt[r][c] = 3
            out["synced"] = _glyph_matches_exit(nxt, out.get("target"))
            out["actions"] += 1
            return nxt, [], out
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
                    upper_cyan = color == 11 and r < len(grid) - 3
                    if color in (0, 1):
                        touched_black = True
                    elif upper_cyan:
                        touched_cyan = True
                    elif color != 3 and not in_panel:
                        floor_legal = False
                    if in_panel:
                        entered_panel = True
        # Reaching the panel target is only sufficient when the large glyph
        # has the panel's exact screen orientation. Evidence 167 shows that a
        # half-turn match is rejected as a free, non-moving gate contact.
        at_target = target is not None and (nr0, nc0) == target
        if at_target:
            exact = False
            red = []
            h = len(grid)
            w = len(grid[0]) if h else 0
            for r in range(h):
                for c in range(w):
                    if grid[r][c] == 9 and r > (3 * h) // 4 and c < w // 3:
                        red.append((r, c))
            if red:
                rr0 = min(p[0] for p in red)
                cc0 = min(p[1] for p in red)
                large = []
                small = []
                tr, tc = target
                for rr in range(3):
                    for cc in range(3):
                        filled = False
                        for r in range(rr0 + 2 * rr, rr0 + 2 * rr + 2):
                            for c in range(cc0 + 2 * cc, cc0 + 2 * cc + 2):
                                if grid[r][c] == 9:
                                    filled = True
                        large.append(filled)
                        small.append(grid[tr + 1 + rr][tc + 1 + cc] == 9)
                exact = large == small
            if exact:
                out["actions"] += 1
                out["complete"] = True
                return nxt, ["LEVEL_COMPLETE"], out
            out["actions"] += 1
            return nxt, [], out
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
            if touched_black:
                if rate == 1:
                    _sync_large_glyph(nxt)
                    out["synced"] = True
                else:
                    # Vertical switch entry is observed to reflect vertically.
                    # The orthogonal-entry candidate predicts the corresponding
                    # horizontal reflection for a horizontal overlap.
                    kind = "vflip" if dr != 0 else "hflip"
                    _transform_large(nxt, kind)
                    out["synced"] = _glyph_matches_exit(nxt, target)
            if touched_cyan:
                # Cyan rings are one-use recharge sources. Their cyan cells
                # become ordinary floor beneath the actor, so departure does
                # not restore the consumed ring.
                consumed_under = []
                for item in out.get("under", []):
                    color = item[2]
                    if color == 11:
                        color = 3
                    consumed_under.append((item[0], item[1], color))
                out["under"] = consumed_under
                for r, c in out.get("timer_cells", []):
                    nxt[r][c] = 11
                out["synced"] = _glyph_matches_exit(nxt, target)
    touched_switch = touched_black or touched_cyan
    # First-level activation and cyan recharge are free; the current level's
    # black transform consumes an ordinary timed action.
    free_switch = moved and ((touched_switch and rate == 1) or touched_cyan)
    if not free_switch:
        _advance_bar(nxt, rate)
    out["actions"] += 1
    return nxt, [], out


def is_goal(latent, grid):
    return bool(latent.get("complete"))
