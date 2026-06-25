"""Claude-as-generator helper: turn a Claude-authored SPEC (tower anchors + heights, per the
EXPERIENCES library) into a valid layout cell-set. Claude makes the generative/structural
decision (where anchors go, how deep, diagonal-for-shapes, symmetric); this code only renders
coordinates with the +0.5 alternating stagger + support cleanup. Reward via validate_prior/EDA.

spec = list of [x, y, height] anchors (integer base coords). mirror=True adds symmetry across
`axis` (vertical=left-right, horizontal=top-bottom). Symmetry is always MEASURED on all 4 axes
(see geom.sym_scores) and reported — gen-layout ranks/prioritises symmetry but never forces it.
Usage (programmatic): from claude_compose import compose; cells = compose(spec, mirror=True)
"""
import json, sys, os, argparse


def compose(spec, mirror=True, axis="vertical", trim_mode="clean"):
    # trim_mode (mirror=False only): "clean" drops highest exposed tops; "shallow" drops the
    # LOWEST exposed tops first -> protects deep feature towers (region-depth beak/eye).
    # mirror seeds the second half across the chosen axis (vertical: -x ; horizontal: -y)
    anchors = {}
    for x, y, h in spec:
        anchors[(x, y)] = max(1, int(h))
        if mirror:
            mx, my = (-x, y) if axis == "vertical" else (x, -y)
            anchors[(mx, my)] = max(anchors.get((mx, my), 1), max(1, int(h)))
    cells = []
    for (ax, ay), h in anchors.items():
        for L in range(h):
            s = 0.5 if (L % 2) else 0.0
            cells.append((L, round(ax + s, 2), round(ay - s, 2)))
    cells = list({c for c in cells})
    # support cleanup: every L>0 cell must overlap >=1 cell directly below (game rule)
    changed = True
    while changed:
        changed = False
        by = {}
        for L, x, y in cells: by.setdefault(L, []).append((x, y))
        keep = []
        for (L, x, y) in cells:
            if L == 0 or any(abs(x - bx) < 1 and abs(y - by_) < 1 for (bx, by_) in by.get(L - 1, [])):
                keep.append((L, x, y))
            else:
                changed = True
        cells = keep
    from geom import geom_symmetrize, geom_div3_trim, clean_div3_trim, clean_div3_trim_shallow
    if mirror:
        # EXACT symmetry (BUGLOG B5): the old "drop topmost-farthest" trim removed 1-2 lone cells
        # -> "a few cells off". Re-impose geometric symmetry on `axis`, then trim by dropping mirror
        # PAIRS (or one on-axis cell for %3==1) so the result stays exactly symmetric.
        cells = geom_div3_trim(geom_symmetrize(cells, axis=axis), axis=axis)
        if axis == "vertical":
            ys = [c[2] for c in cells]
            cy = round((min(ys) + max(ys)) / 2 * 2) / 2      # axis stays at x=0; recentre y only
            return [(L, x, round(y - cy, 2)) for (L, x, y) in cells]
        xs = [c[1] for c in cells]
        cx = round((min(xs) + max(xs)) / 2 * 2) / 2          # axis stays at y=0; recentre x only
        return [(L, round(x - cx, 2), y) for (L, x, y) in cells]
    # asymmetric / elongated (mirror=False, e.g. a tilted sword): drop exposed tops, no sym constraint
    cells = clean_div3_trim_shallow(cells) if trim_mode == "shallow" else clean_div3_trim(cells)
    xs = [c[1] for c in cells]; ys = [c[2] for c in cells]
    cx = round((min(xs) + max(xs)) / 2 * 2) / 2; cy = round((min(ys) + max(ys)) / 2 * 2) / 2
    return [(L, round(x - cx, 2), round(y - cy, 2)) for (L, x, y) in cells]


def to_layout_json(cells, name, path):
    by = {}
    for L, x, y in cells: by.setdefault(L, []).append({"x": x, "y": y})
    layers = [{"index": L, "stones": by[L]} for L in sorted(by)]
    data = {"group": 1, "tiles": "", "layers": layers, "stacks": [],
            "metadata": {"layout": name, "source": "claude_compose", "n_layers": len(layers),
                         "total_tiles": len(cells), "capacity": len(cells) // 3,
                         "divisible_by_3": len(cells) % 3 == 0}}
    json.dump(data, open(path, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    return data
