# Object-level motion model grounded by transitions 1-3.
# The 12/9 five-cell tile is movable; actions 1/2 are vertical and 3 moves left.

def _cells(grid, colors):
    out = []
    for r, row in enumerate(grid):
        for c, value in enumerate(row):
            if value in colors:
                out.append((r, c, value))
    return out


def _target_box(grid):
    cells = _cells(grid, (12,))
    if not cells:
        return None
    rows = [cell[0] for cell in cells]
    cols = [cell[1] for cell in cells]
    c0 = min(cols)
    size = max(cols) - c0 + 1
    return min(rows), c0, size


def _nine_components(grid):
    seen = set()
    parts = []
    height = len(grid)
    width = len(grid[0])
    for r in range(height):
        for c in range(width):
            if grid[r][c] != 9 or (r, c) in seen:
                continue
            part = []
            stack = [(r, c)]
            seen.add((r, c))
            while stack:
                rr, cc = stack.pop()
                part.append((rr, cc))
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr = rr + dr
                    nc = cc + dc
                    if 0 <= nr < height and 0 <= nc < width:
                        if grid[nr][nc] == 9 and (nr, nc) not in seen:
                            seen.add((nr, nc))
                            stack.append((nr, nc))
            parts.append(part)
    return parts


def _glyphs_match(grid):
    small = None
    large = None
    for part in _nine_components(grid):
        rows = [cell[0] for cell in part]
        cols = [cell[1] for cell in part]
        h = max(rows) - min(rows) + 1
        w = max(cols) - min(cols) + 1
        if h == 3 and w == 3:
            small = part
        elif h == 6 and w == 6:
            large = part
    if small is None or large is None:
        return False
    small_set = set(small)
    large_set = set(large)
    sr0 = min([cell[0] for cell in small])
    sc0 = min([cell[1] for cell in small])
    lr0 = min([cell[0] for cell in large])
    lc0 = min([cell[1] for cell in large])
    for rr in range(3):
        for cc in range(3):
            small_on = (sr0 + rr, sc0 + cc) in small_set
            large_on = True
            for dy in range(2):
                for dx in range(2):
                    if (lr0 + 2 * rr + dy, lc0 + 2 * cc + dx) not in large_set:
                        large_on = False
            if small_on != large_on:
                return False
    return True


def _reflect_lower_panel(grid):
    # The first observed glyph was symmetric enough that a clockwise quarter
    # turn looked like a horizontal reflection.  Level 2 disambiguates it.
    # Locate the six consecutive 5/9 display rows inside the bottom 10-cell
    # panel and rotate their six-cell glyph square 90 degrees clockwise.
    panel_rows = []
    for r, row in enumerate(grid):
        if len(row) > 11 and row[0] == 4 and row[11] == 4:
            valid = True
            has_nine = False
            for value in row[1:11]:
                if value not in (5, 9):
                    valid = False
                if value == 9:
                    has_nine = True
            if valid and has_nine:
                panel_rows.append(r)
    if len(panel_rows) == 6 and panel_rows[5] - panel_rows[0] == 5:
        c0 = len(grid[0])
        c1 = -1
        for r in panel_rows:
            for c in range(1, 11):
                if grid[r][c] == 9:
                    c0 = min(c0, c)
                    c1 = max(c1, c)
        if c1 - c0 + 1 == 6:
            old = []
            for r in panel_rows:
                old.append(grid[r][c0:c0 + 6])
            for rr in range(6):
                for cc in range(6):
                    grid[panel_rows[rr]][c0 + cc] = old[5 - cc][rr]
    # In the current layout every successful translation, including switch
    # entry, consumes two bar cells.  Level 1 has no non-UI color-11 glyphs
    # and retains its observed zero-cost switch behavior.
    first_ui_row = max(0, len(grid) - 4)
    for r in range(first_ui_row):
        if 11 in grid[r]:
            _advance_bar(grid)
            break


def _move_target(grid, dr, dc):
    box = _target_box(grid)
    if box is None:
        return 0
    r0, c0, size = box
    nr0 = r0 + dr
    nc0 = c0 + dc
    if nr0 < 0 or nc0 < 0:
        return 0
    if nr0 + size > len(grid) or nc0 + size > len(grid[0]):
        return 0
    destination = []
    for r in range(nr0, nr0 + size):
        for c in range(nc0, nc0 + size):
            destination.append(grid[r][c])
    switch_contact = False
    glyph_contact = False
    for value in destination:
        if value in (0, 1):
            switch_contact = True
        if value == 9:
            glyph_contact = True
    move_kind = 0
    if switch_contact:
        move_kind = 2
        for value in destination:
            if value not in (0, 1, 3, 5):
                return 0
    elif glyph_contact and _glyphs_match(grid):
        move_kind = 3
        for value in destination:
            if value not in (3, 5, 9):
                return 0
    else:
        move_kind = 1
        for value in destination:
            if value not in (3, 5):
                return 0
    payload = []
    for r in range(r0, r0 + size):
        payload.append(grid[r][c0:c0 + size])
    for r in range(r0, r0 + size):
        for c in range(c0, c0 + size):
            grid[r][c] = 3
    for rr in range(size):
        for cc in range(size):
            grid[nr0 + rr][nc0 + cc] = payload[rr][cc]
    return move_kind


def _advance_bar(grid):
    # Later levels reuse color 11 for maze glyphs.  The consumable status bar
    # remains in the bottom UI rows, so ordinary motion must not erase glyphs.
    first_ui_row = max(0, len(grid) - 4)
    # The first layout consumed one cell per move; the current layout, marked
    # by compact non-UI color-11 glyphs, consumes two.  This visual proxy keeps
    # both observed levels predictive without relying on an external level id.
    amount = 1
    for r in range(first_ui_row):
        if 11 in grid[r]:
            amount = 2
            break
    for r in range(first_ui_row, len(grid)):
        row = grid[r]
        removed = 0
        for c, value in enumerate(row):
            if value == 11 and removed < amount:
                row[c] = 3
                removed += 1


def init_state(entry_grid):
    return {
        "target": _cells(entry_grid, (12,)),
        "marker": _cells(entry_grid, (0, 1)),
        "observed_actions": {1: "target up", 2: "target down", 3: "target left", 4: "target right"},
        "last_move": None,
        "goal": False,
    }


def predict(latent, grid, action):
    aid = int(action["id"])
    nxt = deepcopy(grid)
    move_kind = 0
    box = _target_box(nxt)
    if box is not None:
        size = box[2]
        if aid == 1:
            move_kind = _move_target(nxt, -size, 0)
        elif aid == 2:
            move_kind = _move_target(nxt, size, 0)
        elif aid == 3:
            move_kind = _move_target(nxt, 0, -size)
        elif aid == 4:
            move_kind = _move_target(nxt, 0, size)
    if move_kind == 1:
        _advance_bar(nxt)
    elif move_kind == 2:
        _reflect_lower_panel(nxt)
    # The marker is persistent terrain hidden beneath the tile. Restore it when
    # a successful move vacates the marker footprint.
    if move_kind != 0 and box is not None:
        r0, c0, size = box
        for mr, mc, value in latent["marker"]:
            if r0 <= mr < r0 + size and c0 <= mc < c0 + size:
                nxt[mr][mc] = value
    events = []
    if move_kind == 3:
        events = ["LEVEL_COMPLETE"]
    nxt_latent = deepcopy(latent)
    nxt_latent["target"] = _cells(nxt, (12,))
    nxt_latent["last_move"] = (aid, move_kind)
    nxt_latent["goal"] = move_kind == 3
    return nxt, events, nxt_latent


def is_goal(latent, grid):
    return bool(latent.get("goal", False))
