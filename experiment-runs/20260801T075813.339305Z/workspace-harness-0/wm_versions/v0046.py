# Object-level model grounded by observed transitions across levels.


def _purple_tile(grid):
    # Ground the movable actor as a solid 5x5 bicolour tile. Later levels can
    # contain additional purple display glyphs, so a global purple bounding box
    # incorrectly joins unrelated objects. Levels 2 and 3 show the actor as the
    # unique solid 5x5 block made from colours 12 and 9; evidence 337 confirms
    # that this component moves as one tile in level 3.
    h = len(grid)
    w = len(grid[0]) if h else 0
    for r0 in range(max(0, h - 4)):
        for c0 in range(max(0, w - 4)):
            has_purple = False
            has_red = False
            solid = True
            for r in range(r0, r0 + 5):
                for c in range(c0, c0 + 5):
                    color = grid[r][c]
                    if color not in (9, 12):
                        solid = False
                    elif color == 12:
                        has_purple = True
                    else:
                        has_red = True
            if solid and has_purple and has_red:
                return (r0, c0, r0 + 4, c0 + 4)

    # Compatibility fallback for the first level, where purple alone was a
    # sufficient actor marker.
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
    # cells from each timer row per ordinary action; the earlier level without
    # it consumed one cell per row.
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
    # Transform the doubled glyph inside the lower-left display as one object.
    # Earlier levels used red; level 3 uses purple for the same display role.
    cells = []
    glyph_color = 9
    h = len(grid)
    for r in range(h):
        for c in range(len(grid[r])):
            if grid[r][c] == glyph_color and r > (3 * h) // 4 and c < len(grid[r]) // 3:
                cells.append((r, c))
    if not cells:
        glyph_color = 12
        for r in range(h):
            for c in range(len(grid[r])):
                if grid[r][c] == glyph_color and r > (3 * h) // 4 and c < len(grid[r]) // 3:
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
            rr = r
            cc = c1 - (c - c0)
        grid[rr][cc] = glyph_color


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
    cells = []
    glyph_color = 9
    h = len(grid)
    for r in range(h):
        for c in range(len(grid[r])):
            if grid[r][c] == glyph_color and r > (3 * h) // 4 and c < len(grid[r]) // 3:
                cells.append((r, c))
    if not cells:
        # Level 3 recolours the large display purple while retaining the red
        # target. Panel admission must use the display's actual colour just as
        # the exact target-contact check does.
        glyph_color = 12
        for r in range(h):
            for c in range(len(grid[r])):
                if grid[r][c] == glyph_color and r > (3 * h) // 4 and c < len(grid[r]) // 3:
                    cells.append((r, c))
    if not cells:
        return False
    r0 = min(p[0] for p in cells)
    c0 = min(p[1] for p in cells)
    large = []
    small = []
    tr, tc = target
    for rr in range(3):
        for cc in range(3):
            filled = False
            for r in range(r0 + 2 * rr, r0 + 2 * rr + 2):
                for c in range(c0 + 2 * cc, c0 + 2 * cc + 2):
                    if grid[r][c] == glyph_color:
                        filled = True
            large.append(filled)
            small.append(grid[tr + 1 + rr][tc + 1 + cc] == 9)
    # Panel-lip traversal accepts reflection-family alignment. Evidence 165
    # established half-turn admission, and evidence 271 directly established
    # admission of the target's top-bottom reflection. Completion remains
    # stricter: the target-contact branch independently checks exact equality.
    top_bottom = small[6:9] + small[3:6] + small[0:3]
    left_right = []
    for rr in range(3):
        row = small[3 * rr:3 * rr + 3]
        left_right.extend(list(reversed(row)))
    return (large == small or large == list(reversed(small)) or
            large == top_bottom or large == left_right)


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
    # This counter is diagnostic only. Keep it depth-invariant so exact search
    # can merge otherwise identical revisited states.
    out["actions"] = 0
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
                # Evidence 290 shows that the terminal timeout input still
                # executes an ordinary legal movement before GAME_OVER.
                for r, c in reserve_cells:
                    nxt[r][c] = 3
                if box is not None and delta is not None:
                    r0, c0, r1, c1 = box
                    dr, dc = delta
                    nr0 = r0 + dr
                    nc0 = c0 + dc
                    legal = nr0 >= 0 and nc0 >= 0
                    legal = legal and nr0 + 4 < len(grid)
                    legal = legal and nc0 + 4 < len(grid[0])
                    if legal:
                        for r in range(nr0, nr0 + 5):
                            for c in range(nc0, nc0 + 5):
                                if grid[r][c] != 3:
                                    legal = False
                    if legal:
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
            purple_display = []
            for r in range(h):
                for c in range(w // 3):
                    if r > (3 * h) // 4 and nxt[r][c] == 12:
                        purple_display.append((r, c))
            if purple_display:
                # Evidence 370 shows that a level-3 timeout restores the
                # purple entry glyph. Its reusable object relation is the
                # target glyph rotated by 180 degrees.
                pr0 = min(p[0] for p in purple_display)
                pc0 = min(p[1] for p in purple_display)
                for r, c in purple_display:
                    nxt[r][c] = 5
                target = out.get("target")
                if target is not None:
                    tr, tc = target
                    for rr in range(3):
                        for cc in range(3):
                            if nxt[tr + 1 + rr][tc + 1 + cc] == 9:
                                dr = 2 - rr
                                dc = 2 - cc
                                for r in range(pr0 + 2 * dr, pr0 + 2 * dr + 2):
                                    for c in range(pc0 + 2 * dc, pc0 + 2 * dc + 2):
                                        nxt[r][c] = 12
            else:
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

        # Level 3 contains a blue-edged corridor portal. Evidence 344 shows
        # that entering the green tile immediately right of a five-cell blue
        # boundary transports the actor to the farthest complete green tile in
        # that horizontal corridor. The extra static purple display identifies
        # this layout without changing earlier level behavior.
        purple_count = 0
        for rr in range(len(grid)):
            for cc in range(len(grid[rr])):
                if grid[rr][cc] == 12:
                    purple_count += 1
        portal_entry = rate == 2 and purple_count > 20
        portal_entry = portal_entry and nr0 >= 0 and nc0 > 0
        portal_entry = portal_entry and nr0 + 4 < len(grid)
        if portal_entry:
            for rr in range(nr0, nr0 + 5):
                if grid[rr][nc0 - 1] != 1:
                    portal_entry = False
        if portal_entry:
            far = nc0
            width = len(grid[0]) if grid else 0
            while far + 9 < width:
                candidate = far + 5
                clear = True
                for rr in range(nr0, nr0 + 5):
                    for cc in range(candidate, candidate + 5):
                        if grid[rr][cc] != 3:
                            clear = False
                if not clear:
                    break
                far = candidate
            nc0 = far

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
        # has the panel's exact screen orientation. Evidence 167 rejected a
        # half-turn, and evidence 272 rejected a top-bottom reflection; both
        # contacts were free, non-moving gate interactions.
        at_target = target is not None and (nr0, nc0) == target
        if at_target:
            exact = False
            display = []
            glyph_color = 9
            h = len(grid)
            w = len(grid[0]) if h else 0
            for r in range(h):
                for c in range(w):
                    if grid[r][c] == glyph_color and r > (3 * h) // 4 and c < w // 3:
                        display.append((r, c))
            if not display:
                # Level 3 recolours the large display purple while retaining
                # the red target as the orientation reference.
                glyph_color = 12
                for r in range(h):
                    for c in range(w):
                        if grid[r][c] == glyph_color and r > (3 * h) // 4 and c < w // 3:
                            display.append((r, c))
            if display:
                rr0 = min(p[0] for p in display)
                cc0 = min(p[1] for p in display)
                large = []
                small = []
                tr, tc = target
                for rr in range(3):
                    for cc in range(3):
                        filled = False
                        for r in range(rr0 + 2 * rr, rr0 + 2 * rr + 2):
                            for c in range(cc0 + 2 * cc, cc0 + 2 * cc + 2):
                                if grid[r][c] == glyph_color:
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
                    # Switch entry is side-sensitive and level-specific. In
                    # level 3, entry from the right or below reflects top-to-bottom,
                    # while entry from the left reflects left-to-right.
                    # Alignment is always recomputed from the resulting pixels:
                    # composing different reflections need not immediately make
                    # the glyph exact in every encountered orientation.
                    if purple_count > 20 and dr < 0:
                        # The latest below-entry observation changed only the
                        # top and bottom glyph rows: level-3 entry from below
                        # therefore applies a top-bottom reflection, not the
                        # previously conjectured two-axis composition.
                        _transform_large(nxt, "vflip")
                        out["synced"] = _glyph_matches_exit(nxt, target)
                    else:
                        if purple_count > 20:
                            # Evidence 360-362 grounds the horizontal mapping:
                            # right-side entry is top-bottom reflection and
                            # left-side entry is left-right reflection.
                            kind = "vflip" if dc < 0 else "hflip"
                        else:
                            kind = "hflip" if dc < 0 else "vflip"
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
    # Search completion requires exact target contact; reflection-family panel
    # admission alone is never a goal state.
    return bool(latent.get("complete"))
