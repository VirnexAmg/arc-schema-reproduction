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
                    cell = g[yy][xx]
                    # Red inside the main maze is a collectible and may be
                    # entered. Red elsewhere (notably the upper lock) is solid.
                    maze_red = cell == 9 and 25 <= yy < 50
                    if (xx, yy) not in old_cells and cell not in (0, 1, 3, 5) and not maze_red:
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

            # Crossing downward from the horizontal hall into the lower corridor
            # activates the bottom-left status glyph and waives this step's meter
            # cost.  This is an entry event, not collection of a maze object.
            if aid == 2 and box[1] == 30:
                picked_key = True
                st["lower_corridor_entered"] = True
                if len(g) > 58:
                    for yy in (57, 58):
                        for xx in (3, 4):
                            if xx < len(g[yy]) and g[yy][xx] == 9:
                                g[yy][xx] = 5
                        # The status glyph changes from its left-facing segment
                        # to the corresponding right-side segment.
                        for xx in (7, 8):
                            if xx < len(g[yy]):
                                g[yy][xx] = 9

            # The red 5x5 object in the maze is collected by becoming
            # orthogonally adjacent; it is distinct from the avatar's red body.
            # Collection clears it to green and updates the matching HUD glyph.
            target = st.get("target", [])
            # Only the red component inside the main maze is collectible.  Other
            # red cells encode the upper lock and HUD and must remain intact.
            maze_target = [(tx, ty) for tx, ty in target if 25 <= ty < 50]
            touched = False
            for tx, ty in maze_target:
                overlap = box[0] <= tx <= box[2] and box[1] <= ty <= box[3]
                adjacent = (box[0] <= tx <= box[2] and (ty == box[1] - 1 or ty == box[3] + 1)) or (box[1] <= ty <= box[3] and (tx == box[0] - 1 or tx == box[2] + 1))
                if overlap or adjacent:
                    touched = True
            if touched:
                picked_key = True
                for tx, ty in maze_target:
                    if 0 <= ty < len(g) and 0 <= tx < len(g[ty]):
                        g[ty][tx] = 3
                st["target"] = [(tx, ty) for tx, ty in target if not (25 <= ty < 50)]
                # The avatar remains visible over the collected red object, and
                # its saved substrate must become green for the later departure.
                for tx, ty in maze_target:
                    key = str(tx) + "," + str(ty)
                    if key in new_under:
                        new_under[key] = 3
                for yy in range(box[1], box[1] + 2):
                    for xx in range(box[0], box[0] + 5):
                        g[yy][xx] = 12
                for yy in range(box[1] + 2, box[1] + 5):
                    for xx in range(box[0], box[0] + 5):
                        g[yy][xx] = 9
                st["under"] = new_under
                if len(g) > 58:
                    for yy in (57, 58):
                        for xx in (3, 4):
                            if xx < len(g[yy]) and g[yy][xx] == 9:
                                g[yy][xx] = 5

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
