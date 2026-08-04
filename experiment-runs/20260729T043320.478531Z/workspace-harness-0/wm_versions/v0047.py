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
    targets = _target_cells(entry_grid, box)
    # The isolated 5x5 red pad in the lower maze is the timeout checkpoint.
    # Preserve its reusable location even after the pad is collected/painted over.
    maze_red = [(x, y) for x, y in targets if 25 <= y < 50]
    checkpoint = None
    if maze_red:
        # color 9 is the lower three rows of the 5x5 pad; its visual origin is
        # therefore two rows above the minimum color-9 coordinate.
        checkpoint = (min(x for x, y in maze_red), min(y for x, y in maze_red) - 2)
    return {
        "box": box,
        "under": {},
        "target": targets,
        "checkpoint": checkpoint,
        # Timeout returns the avatar to its level-entry spawn. This is more
        # reliable than treating every lower red cell as the respawn origin.
        "spawn": (box[0], box[1]) if box is not None else checkpoint,
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

def _meter_empty(g):
    if len(g) < 63:
        return False
    return not any(v == 11 for v in g[61])

def _timeout_reset(g, st, box):
    # An input made after the cyan action meter is exhausted is a puzzle timeout,
    # not a life boundary.  It restores the lower checkpoint and the full meter.
    # At timeout the maze checkpoint is rebuilt, so clear the old avatar to
    # corridor floor rather than relying on potentially stale saved substrate.
    if box is not None:
        for yy in range(box[1], box[3] + 1):
            for xx in range(box[0], box[2] + 1):
                g[yy][xx] = 3
    # Reset also clears the lower red checkpoint/object footprint.  Historical
    # timeout frames contain only the respawned avatar immediately to its left;
    # retaining the old five-cell object produced a second red block.
    cp = st.get("checkpoint")
    if cp is not None:
        for yy in range(cp[1], cp[1] + 5):
            for xx in range(cp[0], cp[0] + 5):
                g[yy][xx] = 3
    # The exhaustion-triggering input is swallowed by the reset. Respawn on the
    # preserved lower red checkpoint; do not apply that input as movement.
    cp = st.get("checkpoint")
    if cp is not None:
        # Respawn directly on the lower 5x5 checkpoint pad. In full-row RLE the
        # four-cell gray border shifts visual x counts; the observed origin is
        # the pad origin itself, not the cell immediately to its left.
        nx, ny = cp
    else:
        nx, ny = (34, 45)
    new_under = {}
    for yy in range(ny, ny + 5):
        for xx in range(nx, nx + 5):
            new_under[str(xx) + "," + str(yy)] = g[yy][xx]
            g[yy][xx] = 12 if yy < ny + 2 else 9
    # Restore the ten-cell status glyph and 42-column cyan budget.
    for yy in range(55, 61):
        for xx in range(1, 11):
            g[yy][xx] = 5
    for yy in (55, 56):
        for xx in range(3, 9): g[yy][xx] = 9
    for yy in (57, 58):
        for xx in (3, 4): g[yy][xx] = 9
    for yy in (59, 60):
        for xx in (3, 4, 7, 8): g[yy][xx] = 9
    for yy in (61, 62):
        for xx in range(13, 55): g[yy][xx] = 11
        g[yy][55] = 5
        for xx in range(56, 64):
            if g[yy][xx] == 11: g[yy][xx] = 3
    # Timeout clears the final two-cell direction indicator as in the reset HUD.
    for yy in (61, 62):
        g[yy][62] = 3
        g[yy][63] = 3
    st["box"] = (nx, ny, nx + 4, ny + 4)
    st["under"] = new_under
    st["symbol_activated"] = False
    # Timeout restores position and the visible HUD, but does not erase the
    # corridor-entry phase of the puzzle's directional finite-state machine.
    # The later post-timeout downward entry is therefore a repeated (paid)
    # transition rather than another first-entry interaction.
    return g, [], st

def predict(latent, grid, action):
    g = deepcopy(grid)
    st = deepcopy(latent)
    box = _token_box(grid)
    if _meter_empty(grid):
        return _timeout_reset(g, st, box)
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
            # The blue/black glyph is passable substrate and is restored after
            # the avatar leaves, but overlapping it rotates/toggles the matching
            # bottom-left status glyph.  Detect it before painting the avatar.
            # The small blue/black switch is activated when the avatar becomes
            # edge-adjacent to it; overlap is not required.  This explains the
            # observed left move to x=19 beside the glyph ending at x=18.
            crossed_symbol = False
            for yy in range(ny - 1, ny + 6):
                for xx in range(nx - 1, nx + 6):
                    if 0 <= yy < len(g) and 0 <= xx < len(g[yy]):
                        if g[yy][xx] in (0, 1):
                            crossed_symbol = True
            picked_key = False
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

            # Contact with a side of the blue/black switch records the approach
            # direction in the matching HUD segment.  The newly observed upward
            # approach (from below) shifts the middle segment right and is a
            # free interaction, just like other switch/checkpoint contacts.
            if aid == 1 and crossed_symbol:
                picked_key = True
                st["symbol_activated"] = True
                if len(g) > 58:
                    for yy in (57, 58):
                        for xx in range(1, 11):
                            g[yy][xx] = 5
                        for xx in (7, 8):
                            g[yy][xx] = 9

            # Horizontal crossings record the outer HUD rows. The first
            # observed right-to-left contact did this before activation; the
            # later left-to-right contact did it even after an upward contact.
            horizontal_contact = (aid == 3 and not st.get("symbol_activated", False)) or aid == 4
            if horizontal_contact and crossed_symbol:
                st["symbol_activated"] = True
                if len(g) > 60:
                    for yy in (55, 56):
                        for xx in range(1, 11):
                            g[yy][xx] = 5
                        for xx in (3, 4, 7, 8):
                            g[yy][xx] = 9
                    for yy in (59, 60):
                        for xx in range(1, 11):
                            g[yy][xx] = 5
                        for xx in range(3, 9):
                            g[yy][xx] = 9
                # Repeated left-to-right approaches advance the switch's
                # directional display.  The first such contact preserves the
                # middle pair established by an upward approach; the second
                # returns that pair to the left side.  Count contacts rather
                # than keying this effect to a board coordinate so the same
                # finite-state mechanism can transfer to later layouts.
                if aid == 4:
                    right_contacts = st.get("right_contacts", 0) + 1
                    st["right_contacts"] = right_contacts
                    if right_contacts >= 2 and len(g) > 58:
                        for yy in (57, 58):
                            for xx in range(1, 11):
                                g[yy][xx] = 5
                            for xx in (3, 4):
                                g[yy][xx] = 9

            # Downward entry into this corridor advances the middle direction
            # display.  The first entry selects the right pair and is a free
            # checkpoint interaction; later entries select the left pair and
            # remain ordinary paid moves.  This stateful rule explains both the
            # earlier first-entry observation and the latest repeated entry.
            if aid == 2 and box[1] == 30:
                first_entry = not st.get("lower_corridor_entered", False)
                st["lower_corridor_entered"] = True
                if first_entry:
                    picked_key = True
                if len(g) > 60:
                    # First entry changes only the middle pair because the outer
                    # rows are already at their reset pattern. A repeated entry
                    # resets the complete six-row glyph, revealing that this is
                    # a reset transition rather than an isolated middle toggle.
                    if not first_entry:
                        for yy in range(55, 61):
                            for xx in range(1, 11):
                                g[yy][xx] = 5
                        for yy in (55, 56):
                            for xx in range(3, 9):
                                g[yy][xx] = 9
                        for yy in (59, 60):
                            for xx in (3, 4, 7, 8):
                                g[yy][xx] = 9
                    for yy in (57, 58):
                        for xx in range(1, 11):
                            g[yy][xx] = 5
                        pair = (7, 8) if first_entry else (3, 4)
                        for xx in pair:
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
    # Corridor-entry / collectible interactions waive the meter tick.  This
    # explains the observed downward move into y=30: the avatar and HUD changed,
    # but the action-cost strip did not advance.
    # Once the directional switch has been activated, even blocked inputs consume
    # a meter tick.  Before activation, the observed blocked upward door attempt
    # was free, while ACTION2 still consumed a tick.
    # Pressing upward while already seated against the upper lock is a free
    # interaction attempt: unlike ordinary blocked inputs after switch
    # activation, it does not consume the action-cost meter.
    at_upper_lock = box is not None and aid == 1 and box[1] == 15 and not moved
    # Every ordinary input spends a budget tick, including a collision with a
    # maze wall.  The earlier ACTION1 exception was overgeneralized from the
    # upper-door interaction: only that spatially grounded lock attempt is free.
    if aid in moves and not picked_key and not at_upper_lock:
        _advance_meter(g)
    return g, [], st

def is_goal(latent, grid):
    return False
