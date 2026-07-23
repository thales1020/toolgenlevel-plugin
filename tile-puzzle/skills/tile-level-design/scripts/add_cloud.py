"""POST-TILE overlay: mark normal tiles as CLOUD (`o:[1]`) on a COMPLETE level.

CLOUD tile (confirmed from game-data/CloudTile/): a normal match-3 tile (i, x, y — real colour,
matchable, counts toward ÷3) carrying an extra stone field `"o":[1]`. It is COVERED by the
`tile_cover_mystery.png` art while covered, and the cover clears MISSION-STYLE — the instant nothing on
a HIGHER layer overlaps it (i.e. exactly when it becomes pickable), revealing the real face. It is a
normal tile underneath, so it changes NOTHING about geometry / match-3 balance / solvability (the
solver ignores `o`). The `o` value encodes type: **1 = cloud** (this tool); 0 = mystery (a FUTURE
variant, not implemented here).

Placement rule (spec PHẦN 6): clouds are ~15-20% of tiles, on the BOTTOM layer(s) only (0-1, NEVER the
top — a cloud must start covered), 100% covered-at-start. Candidate cells must be COVERED (a higher tile
overlaps, so it starts under a cover) AND VISIBLE (no tile sits directly on top — the cover PEEKS out);
this needs a STAGGERED layout (gen-layout's default `uniform_stagger`) — on a COLUMNAR layout every
bottom cell is fully hidden and no clouds can be placed.

Symmetry is HYBRID (spec bug #10 — the old hard-symmetry gate left 79/301 cloud levels with 0 clouds):
PASS 1 fills from symmetric ORBITS inner-first (keeps the aesthetic where the geometry allows it); if that
alone can't reach the target, PASS 2 tops up from any covered+visible candidate, inner-first — so the
target coverage is met and the level is NEVER left with 0 clouds. Fully symmetric iff no top-up was needed.

Run this LAST (after tiles + any bonus/mission/mystery). Preserves every other field.

Usage:
  python add_cloud.py <level.json> [--cloud-pct 18 | --cloud N] [--layers 0,1] [--axis auto] [--out ...]
"""
import sys, os, json, argparse


def _mirror(x, y, axis):
    if axis == "vertical":   return [(x, y), (-x, y)]
    if axis == "horizontal": return [(x, y), (x, -y)]
    if axis == "vh":         return [(x, y), (-x, y), (x, -y), (-x, -y)]
    return [(x, y)]


def _covered(L, x, y, all_stones):
    """A cell is covered at start iff some stone on a HIGHER layer overlaps it (|dx|<1 & |dy|<1)."""
    return any(sL > L and abs(sx - x) < 1 and abs(sy - y) < 1 for (sL, sx, sy, _) in all_stones)


def _visible(L, x, y, all_stones, eps=0.5):
    """A cell PEEKS (its cover shows) iff NO higher-layer stone sits directly on top of it — i.e. none is
    within `eps` of (x,y). On a COLUMNAR layout every bottom cell has a tile exactly on top (fully hidden);
    on a STAGGERED layout (odd/even layers offset by 0.5) covered cells peek and the cloud cover is seen."""
    return not any(sL > L and abs(sx - x) < eps and abs(sy - y) < eps for (sL, sx, sy, _) in all_stones)


def main():
    ap = argparse.ArgumentParser(description="Mark normal tiles as CLOUD (o:[1]) — symmetric, bottom-layer, covered-at-start.")
    ap.add_argument("level")
    ap.add_argument("--out", default="")
    ap.add_argument("--cloud", type=int, default=None, help="exact number of cloud tiles (else use --cloud-pct)")
    ap.add_argument("--cloud-pct", type=float, default=18.0, help="target %% of total tiles (default 18; spec 15-20)")
    ap.add_argument("--layers", default="0,1", help="bottom layer indices to place clouds on (default 0,1)")
    ap.add_argument("--axis", choices=("auto", "vertical", "horizontal", "vh"), default="auto",
                    help="symmetry axis for the cloud region (default auto; at least vertical)")
    a = ap.parse_args()

    data = json.load(open(a.level, encoding="utf-8"))
    all_stones = []                       # (layer, x, y, stone-ref)
    for ly in data["layers"]:
        for s in ly.get("stones", []):
            all_stones.append((ly["index"], round(float(s["x"]), 3), round(float(s["y"]), 3), s))
    total = len(all_stones)
    place_layers = {int(v) for v in a.layers.split(",") if v.strip() != ""}

    # candidates = NORMAL (i<1001), not already m/o, on the chosen bottom layers, COVERED at start AND
    # VISIBLE (peeking — no tile directly on top; else the cloud cover is fully hidden and never seen).
    cand = {}
    for (L, x, y, s) in all_stones:
        if L in place_layers and int(s.get("i", 0)) < 1001 and not s.get("m") and not s.get("o"):
            if _covered(L, x, y, all_stones) and _visible(L, x, y, all_stones):
                cand[(L, x, y)] = s
    cand_set = set(cand)

    def valid_orbits(axis):
        """Orbits (same layer, mirrored (x,y)) whose EVERY member is a candidate — keeps the set symmetric."""
        seen, orbits = set(), []
        for (L, x, y) in cand:
            # dedupe members so an on-axis cell (its mirror == itself) is a 1-cell orbit, not double-counted
            orb = tuple(sorted({(L, round(mx, 3), round(my, 3)) for (mx, my) in _mirror(x, y, axis)}))
            if orb in seen:
                continue
            seen.add(orb)
            if all(m in cand_set for m in orb):
                orbits.append(orb)
        return orbits

    if a.axis == "auto":                  # pick the axis that yields the most symmetric-complete cells
        best = None
        for ax in ("vh", "vertical", "horizontal"):
            orbs = valid_orbits(ax)
            cells = sum(len(o) for o in orbs)
            if best is None or cells > best[1]:
                best = (ax, cells, orbs)
        axis, orbits = best[0], best[2]
        if not orbits:                    # safety: fall back to vertical
            axis, orbits = "vertical", valid_orbits("vertical")
    else:
        axis, orbits = a.axis, valid_orbits(a.axis)

    target = a.cloud if a.cloud is not None else round(a.cloud_pct / 100.0 * total)
    orbits.sort(key=lambda o: (min(abs(x) + abs(y) for (_, x, y) in o), o))   # inner-first coherent region

    # PASS 1 — symmetric orbits, inner-first, up to target (whole orbit only, keeps the set symmetric).
    chosen, chosen_set = [], set()
    for orb in orbits:
        if len(chosen) >= target:
            break
        chosen.extend(orb)
        chosen_set.update(orb)
    sym_count = len(chosen)

    # PASS 2 (HYBRID fallback, spec bug #10) — if symmetry alone fell short, top up from ANY covered+visible
    # candidate (inner-first). Breaks perfect symmetry but hits the target and never leaves 0 clouds.
    if len(chosen) < target:
        extras = sorted((k for k in cand if k not in chosen_set),
                        key=lambda k: (abs(k[1]) + abs(k[2]), k))
        for k in extras:
            if len(chosen) >= target:
                break
            chosen.append(k)
            chosen_set.add(k)

    for key in chosen:
        cand[key]["o"] = [1]
    fully_symmetric = (len(chosen) == sym_count)

    out = a.out or a.level.replace(".json", "_cloud.json")
    json.dump(data, open(out, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    pct = round(100 * len(chosen) / total) if total else 0
    sym_note = "symmetric" if fully_symmetric else f"hybrid ({sym_count} symmetric + {len(chosen)-sym_count} top-up)"
    print(f"-> {out}")
    print(f"   {len(chosen)} cloud tiles (o:[1]) = {pct}% of {total} tiles | axis={axis} | "
          f"layers={sorted(place_layers)} | all covered-at-start | {sym_note} | solvability unchanged")
    if len(chosen) < target:
        print(f"   NOTE: {len(chosen)}/{target} placed — the covered+VISIBLE pool on layers "
              f"{sorted(place_layers)} is exhausted. If ~0, the layout is likely COLUMNAR (bottom cells "
              f"fully hidden); use a STAGGERED layout (gen-layout uniform_stagger).")


if __name__ == "__main__":
    main()
