"""Pure layout geometry + symmetry helpers (no bulk, no data banks, stdlib only).

Extracted from the retired bulk generator so the compose path keeps the symmetry-preserving
trim/mirror it relies on, and adds the 4-AXIS symmetry scorer that gen-layout now ranks on.

Coordinate model: cells = [(layer, x, y)]. The build stagger offsets odd layers by +0.5 in x
and -0.5 in y, so a true VISUAL mirror reflects raw cell coords (which flips the odd-layer lean).

Symmetry is MEASURED on four axes (never forced — see SKILL.md "đo & xếp hạng, không ép"):
  vertical   x -> -x   (left-right mirror; the portrait-friendly primary axis)
  horizontal y -> -y   (top-bottom mirror)
  diag_main  (x,y) -> (y,x)
  diag_anti  (x,y) -> (-y,-x)
"""


def _exposed_top(cells):
    """Cells with no higher-layer cell overlapping them (a removable top, never floats anything)."""
    s = list(cells)
    out = []
    for (L, x, y) in s:
        if not any(L2 > L and abs(x2 - x) < 1 and abs(y2 - y) < 1 for (L2, x2, y2) in s):
            out.append((L, x, y))
    return out


# ---------- symmetry measurement (4 axes) ----------
def _mirror(axis):
    """Return the reflection map for one of the 4 axes."""
    if axis == "vertical":
        return lambda c: (c[0], round(-c[1], 2), c[2])
    if axis == "horizontal":
        return lambda c: (c[0], c[1], round(-c[2], 2))
    if axis == "diag_main":
        return lambda c: (c[0], round(c[2], 2), round(c[1], 2))
    if axis == "diag_anti":
        return lambda c: (c[0], round(-c[2], 2), round(-c[1], 2))
    raise ValueError(f"unknown axis {axis!r}")


AXES = ("vertical", "horizontal", "diag_main", "diag_anti")


def sym_scores(cells):
    """Fraction of cells whose mirror image also exists, for each of the 4 axes.
    1.0 = perfectly symmetric on that axis. Cells must be centred (axis through origin)."""
    s = set((int(L), round(x, 2), round(y, 2)) for L, x, y in cells)
    n = len(s) or 1
    out = {}
    for ax in AXES:
        m = _mirror(ax)
        out[ax] = round(sum(1 for c in s if m(c) in s) / n, 3)
    return out


def best_axis(cells):
    """(axis_name, score) of the axis the shape is MOST symmetric on."""
    sc = sym_scores(cells)
    ax = max(sc, key=sc.get)
    return ax, sc[ax]


def geom_sym_frac(cells):
    """Back-compat: vertical-axis symmetry fraction (left-right mirror)."""
    return sym_scores(cells)["vertical"]


def is_geom_sym(cells, axis="vertical"):
    s = set((L, round(x, 2), round(y, 2)) for L, x, y in cells)
    m = _mirror(axis)
    return all(m((L, x, y)) in s for (L, x, y) in s)


# ---------- symmetrize across an orthogonal axis ----------
def geom_symmetrize(cells, axis="vertical"):
    """Keep the dominant half + axis cells, add geometric mirrors -> exactly symmetric on `axis`.
    Supports the two orthogonal axes (vertical x=0, horizontal y=0); diagonals are measured but
    not snapped (rarely useful for portrait shapes)."""
    if axis not in ("vertical", "horizontal"):
        raise ValueError("geom_symmetrize only snaps vertical/horizontal; use sym_scores to rank")
    coord = (lambda x, y: x) if axis == "vertical" else (lambda x, y: y)
    m = _mirror(axis)
    dom = set(); ax = set()
    for (L, x, y) in cells:
        x = round(x, 2); y = round(y, 2)
        c = coord(x, y)
        if c > 0.01:
            dom.add((L, x, y))
        elif abs(c) <= 0.01:
            ax.add((L, x, y))
    full = set(ax) | dom | {m(c) for c in dom}
    return [(L, x, y) for (L, x, y) in full]


def geom_div3_trim(cells, axis="vertical"):
    """Trim to len%3==0 while KEEPING symmetry on `axis`: drop mirror PAIRS of exposed tops (2),
    or one on-axis exposed top for the %3==1 case. Removes only exposed cells (no floating)."""
    on_axis = (lambda c: abs(c[1]) <= 0.01) if axis == "vertical" else (lambda c: abs(c[2]) <= 0.01)
    off_axis = (lambda c: c[1] > 0.01) if axis == "vertical" else (lambda c: c[2] > 0.01)
    m = _mirror(axis)
    s = set((L, round(x, 2), round(y, 2)) for L, x, y in cells)
    guard = 0
    while len(s) % 3 and guard < 300:
        guard += 1
        tops = _exposed_top(s)
        axis_tops = [c for c in tops if on_axis(c)]
        side_tops = [c for c in tops if off_axis(c)]
        if len(s) % 3 == 1 and axis_tops:
            s.discard(max(axis_tops, key=lambda c: c[0]))
        elif side_tops:
            c = max(side_tops, key=lambda c: (c[1] ** 2 + c[2] ** 2))
            s.discard(c); s.discard(m(c))
        elif axis_tops:
            s.discard(max(axis_tops, key=lambda c: c[0]))
        else:
            break
    return [(L, x, y) for (L, x, y) in s]


def _floating(cells):
    """Cells at L>0 with no overlapping cell directly below (would float — invalid)."""
    by = {}
    for L, x, y in cells:
        by.setdefault(L, []).append((x, y))
    out = set()
    for (L, x, y) in cells:
        if L == 0:
            continue
        if not any(abs(x - bx) < 1 and abs(y - by_) < 1 for (bx, by_) in by.get(L - 1, [])):
            out.add((L, x, y))
    return out


def _d4_orbit(cell):
    """Up-to-8 images under the dihedral group D4 (4 reflection axes + rotations):
    x->-x, y->-y, and the two diagonals (x,y)->(y,x) / (x,y)->(-y,-x). Same layer."""
    L, x, y = cell
    return {(L, round(a, 2), round(b, 2)) for (a, b) in
            [(x, y), (-x, y), (x, -y), (-x, -y), (y, x), (-y, x), (y, -x), (-y, -x)]}


def _klein_orbit(cell):
    """4 images under the 2 orthogonal axes only (vertical + horizontal): (±x, ±y). Same layer.
    For objects symmetric left-right AND top-bottom but NOT diagonally (ellipse, eye, rectangle)."""
    L, x, y = cell
    return {(L, round(a, 2), round(b, 2)) for (a, b) in [(x, y), (-x, y), (x, -y), (-x, -y)]}


def _symmetrize_group(cells, orbit_fn):
    """Force EXACT symmetry under the reflection group whose orbit is `orbit_fn`. Union every cell's
    orbit, then REPAIR validity orbit-wise: the +0.5 stagger floats some image cells, so drop any
    floating cell WITH its whole orbit (keeps symmetry) until support is clean; then trim to %3 by
    removing exposed-top orbits. Returns a valid, no-float, div3, symmetric cell set."""
    s = set((int(L), round(x, 2), round(y, 2)) for L, x, y in cells)
    U = set()
    for cell in s:
        U |= orbit_fn(cell)
    guard = 0
    while guard < 400:                                   # repair support, orbit-wise
        guard += 1
        fl = _floating(U)
        if not fl:
            break
        rm = set()
        for cell in fl:
            rm |= orbit_fn(cell)
        U -= rm
    guard = 0
    while len(U) % 3 and guard < 400:                    # trim to %3 by exposed-top orbits
        guard += 1
        tops = _exposed_top(U)
        if not tops:
            break
        U -= orbit_fn(max(tops, key=lambda c: (c[0], c[1] ** 2 + c[2] ** 2)))
    return [(L, x, y) for (L, x, y) in U]


def d4_symmetrize(cells):
    """EXACT 4-axis (D4) symmetry — vertical + horizontal + BOTH diagonals all score 1.00. For
    square/mandala motifs (decorative tiles) whose source object has 4 reflection axes."""
    return _symmetrize_group(cells, _d4_orbit)


def vh_symmetrize(cells):
    """EXACT 2-axis symmetry — vertical AND horizontal both score 1.00 (4 quadrants identical),
    diagonals left as-is. For objects symmetric L-R and T-B but not diagonally."""
    return _symmetrize_group(cells, _klein_orbit)


def clean_div3_trim(cells):
    """Trim to len%3==0 by removing EXPOSED tops only (no floating), highest+farthest first.
    No symmetry constraint -> for the intentionally-asymmetric (elongated/diagonal) path."""
    s = set((int(L), round(x, 2), round(y, 2)) for L, x, y in cells)
    guard = 0
    while len(s) % 3 and guard < 300:
        guard += 1
        tops = _exposed_top(s)
        if not tops:
            break
        s.discard(max(tops, key=lambda c: (c[0], c[1] ** 2 + c[2] ** 2)))
    return [(L, x, y) for (L, x, y) in s]


def clean_div3_trim_shallow(cells):
    """Trim to len%3==0 by removing EXPOSED tops but the LOWEST-layer (shallowest) first — so a deep
    feature tower (a tall beak/eye in region-depth) keeps its top while a 1-2-high body edge is shaved
    instead. No floating (only removes exposed cells)."""
    s = set((int(L), round(x, 2), round(y, 2)) for L, x, y in cells)
    guard = 0
    while len(s) % 3 and guard < 300:
        guard += 1
        tops = _exposed_top(s)
        if not tops:
            break
        s.discard(min(tops, key=lambda c: (c[0], -(c[1] ** 2 + c[2] ** 2))))  # lowest layer, farthest
    return [(L, x, y) for (L, x, y) in s]
