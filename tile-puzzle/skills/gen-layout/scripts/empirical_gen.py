"""Empirical (data-driven) layout generator — the generation step that hand-tuned parametric
code could NOT adapt was moved onto SAMPLING REAL STRUCTURE.

Hand-modeling the joint distribution with gauss params plateaued at 4/8 on KS (features
coupled). Sampling a real board skeleton and perturbing it matches the joint BY CONSTRUCTION.
`templates_bank.json` = 400 real board cell-sets (layer,x,y only — no tiles/theme), abstracted
structural templates. Perturbation keeps outputs novel (not exact copies) while preserving the
real joint stats (symmetry, base density, cluster count, tower profile).

Perturbations operate DIRECTLY on the real cell-set (no lossy skeleton extraction):
  - trim the top of a few towers (height variety, preserves base)
  - drop a symmetric PAIR of base columns (size variety without breaking symmetry)
  - optional whole-board mirror (kept rare; real symmetry already in the template)
At interactive gen-time Claude can pick/perturb a template with judgment — this is the
"move the un-adaptable generation step to Claude/data" decision; code here is the bulk default.
"""
import os, json

# GENERATION ENVELOPE (reject+resample outliers). ±2σ for ~normal metrics (width/height/
# layers); empirical percentile-style bounds for skewed metrics (cells/base) — ±2σ would
# chop the real right tail (cells) or go negative (base). Keeps output inside the real envelope.
ENVELOPE = {
    "width":  (4, 9),      # μ±2σ ≈ 4.1–8.5
    "height": (4, 10),     # μ±2σ ≈ 4.4–9.9
    "layers": (2, 11),     # μ±2σ ≈ 2.3–10.2 (+ rare deep)
    "cells":  (40, 150),   # empirical (μ-2σ=38 .. keeps right tail; p98≈150)
    "base":   (6, 40),     # empirical p~2..p98 (μ-2σ=-3 is nonsense)
}

# Mobile is PORTRAIT: a layout wider than tall doesn't fit the screen (BUGLOG B4). Reject w/h above
# this. Real median aspect ~0.88; 1.05 allows square + rounding slack but kills horizontal bulge.
MAX_ASPECT = 1.05

def _in_envelope(cells):
    by = {}
    for L, x, y in cells: by.setdefault(L, []).append((x, y))
    xs = [c[1] for c in cells]; ys = [c[2] for c in cells]
    w = int(round(max(xs) - min(xs))) + 1; h = int(round(max(ys) - min(ys))) + 1
    if w / h > MAX_ASPECT:                      # horizontally-wide -> off-screen on mobile portrait
        return False
    feats = {"width": w, "height": h, "layers": len(by), "cells": len(cells),
             "base": len(by.get(0, []))}
    return all(ENVELOPE[k][0] <= feats[k] <= ENVELOPE[k][1] for k in ENVELOPE)


_BANK = None
def _bank():
    global _BANK
    if _BANK is None:
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates_bank.json")
        _BANK = json.load(open(p, encoding="utf-8"))
    return _BANK


def _columns(cells):
    """Group cells into towers keyed by base (x,y) rounded to integer footprint."""
    col = {}
    for L, x, y in cells:
        key = (round(x - 0.5 * (L % 2)), round(y + 0.5 * (L % 2)))  # undo stagger -> base anchor
        col.setdefault(key, []).append((L, x, y))
    return col


def sample(rng):
    """Sample a real board, perturb it, return cells [(L,x,y)] (or None if too small)."""
    base_cells = [tuple(c) for c in rng.choice(_bank())]
    col = _columns(base_cells)
    keys = list(col)

    # 1. trim top of a few towers (height variety; base footprint preserved).
    #    Gentle: only ~15% of towers, cut exactly 1 — net cell loss small so total stays ~real(72).
    for k in keys:
        if len(col[k]) > 1 and rng.random() < 0.10:
            col[k] = sorted(col[k])[:-1]

    # 2. rarely drop ONE symmetric pair (size variety, symmetry intact). Lower rate -> keep size.
    if len(keys) > 12 and rng.random() < 0.18:
        k = rng.choice(keys); kx, ky = k
        for kk in {k, (-kx, ky)}:
            col.pop(kk, None)

    # 3. rare whole-board mirror
    cells = [c for col_cells in col.values() for c in col_cells]
    if rng.random() < 0.25:
        cells = [(L, -x, y) for (L, x, y) in cells]

    cells = list({(L, round(x, 2), round(y, 2)) for (L, x, y) in cells})
    # support cleanup: trimming/dropping can orphan a staggered neighbor's cell (a +0.5 cell
    # rests on up to 4 base cells). Iteratively remove any L>0 cell with no overlapping cell in
    # L-1 until stable -> satisfies the game cover rule by construction (no floating).
    changed = True
    while changed:
        changed = False
        by = {}
        for L, x, y in cells: by.setdefault(L, []).append((x, y))
        kept = []
        for (L, x, y) in cells:
            if L == 0 or any(abs(x-bx) < 1 and abs(y-by_) < 1 for (bx, by_) in by.get(L-1, [])):
                kept.append((L, x, y))
            else:
                changed = True
        cells = kept
    if len(cells) < 12:
        return None
    # trim to mult-3 (topmost, farthest) + center
    rem = len(cells) % 3
    if rem:
        top = max(c[0] for c in cells)
        tops = sorted([c for c in cells if c[0] == top], key=lambda c: -(c[1]**2 + c[2]**2))
        drop = set(id(c) for c in tops[:rem]); cells = [c for c in cells if id(c) not in drop]
    if not _in_envelope(cells):           # reject outliers; caller's loop resamples
        return None
    xs = [c[1] for c in cells]; ys = [c[2] for c in cells]
    cx = round((min(xs)+max(xs))/2*2)/2; cy = round((min(ys)+max(ys))/2*2)/2
    return [(L, round(x-cx, 2), round(y-cy, 2)) for (L, x, y) in cells]
