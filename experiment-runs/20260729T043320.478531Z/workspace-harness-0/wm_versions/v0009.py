def _token_box(grid):
    pts = []
    for y, row in enumerate(grid):
        for x, v in enumerate(row):
            if v == 12:
                pts.append((x, y))
    if not pts:
        return None
    x0 = min(p[0] for p in pts)
    y0 = min(p[1] for p in pts)
    return (x0, y0, x0 + 4, y0 + 4)

def _target_cells(grid, box):
    out = []
    for y, row in enumerate(grid):
        for x, v in enumerate(row):
            if v == 9 and (box is None or not (box[0] <= x <= box[2] and box[1] <= y <= box[3])):
                out.append((x, y))
    return out

def init_state(entry_grid):
    box = _token_box(entry_grid)
    return {
        "box": box,
        "under": {},
        "target": _target_cells(entry_grid, box),
        "complete": False
    }

def _advance_meter(g):
    # Each observed input advances the two-row strip by one column.
    if len(g) < 63:
        return
    w = min(len(g[61]), len(g[62]))
    for x in range(w):
        if g[61][x] == 11 and g[62][x] == 11:
            g[61][x] = 3
            g[62][x] = 3
            return

def predict(latent, grid, action):
    g = deepcopy(grid)
    st = deepcopy(latent)
    box = _token_box(grid)
    if box is None:
        box = st.get("box")
    aid = int(action["id"])
    moves = {1: (0, -5), 2: (0, 5), 3: (-5, 0), 4: (5, 0)}
    dx, dy = moves.get(aid, (0, 0))

    moved = False
    picked_key = False
    if box is not None and aid in moves:
        nx, ny = box[0] + dx, box[1] + dy
        old_cells = set()
        for yy in range(box[1], box[3] + 1):
            for xx in range(box[0], box[2] + 1):
                old_cells.add((xx, yy))
        valid = nx >= 0 and ny >= 0 and ny + 4 < len(g) and nx + 4 < len(g[0])
        if valid:
            for yy in range(ny, ny + 5):
                for xx in range(nx, nx + 5):
                    # Floor is green/gray.  The blue/black key glyph is collectible:
                    # entering a cell of it is allowed, unlike the red goal glyph.
                    if (xx, yy) not in old_cells and g[yy][xx] not in (0, 1, 3, 5):
                        valid = False
        if valid:
            moved = True
            # Contact with any part of the blue/black glyph collects it.  Its maze
            # pixels clear to floor and the matching HUD glyph turns red.
            picked_key = False
            for yy in range(ny, ny + 5):
                for xx in range(nx, nx + 5):
                    if g[yy][xx] in (0, 1):
                        picked_key = True
            if picked_key:
                st["has_key"] = True
                for yy in range(len(g)):
                    for xx in range(len(g[yy])):
                        if g[yy][xx] in (0, 1):
                            g[yy][xx] = 3 if yy < 50 else 9
            under = st.get("under", {})
            for yy in range(box[1], box[3] + 1):
                for xx in range(box[0], box[2] + 1):
                    key = str(xx) + "," + str(yy)
                    g[yy][xx] = under.get(key, 3)
            new_under = {}
            for yy in range(ny, ny + 5):
                for xx in range(nx, nx + 5):
                    key = str(xx) + "," + str(yy)
                    if (xx, yy) in old_cells:
                        new_under[key] = under.get(key, 3)
                    else:
                        new_under[key] = g[yy][xx]
            for yy in range(ny, ny + 2):
                for xx in range(nx, nx + 5):
                    g[yy][xx] = 12
            for yy in range(ny + 2, ny + 5):
                for xx in range(nx, nx + 5):
                    g[yy][xx] = 9
            box = (nx, ny, nx + 4, ny + 4)
            st["box"] = box
            st["under"] = new_under

    # A blocked action leaves the frame, including the bottom movement meter,
    # unchanged.  Reaching/overlapping red color 9 is not by itself completion:
    # that hypothesis was falsified by the blocked upward attempt at the door.
    # The meter is an action-cost display, not purely a movement counter.
    # Observations show ACTION2 consumes one tick even when its move is blocked
    # by the central wall, whereas the blocked ACTION1 door attempt consumed none.
    if moved or aid == 2:
        _advance_meter(g)
    return g, [], st

def is_goal(latent, grid):
    return False
