"""Evaluate whether a mask (icon footprint) is SIMPLE enough to become a layout.

Computes metrics, prints a verdict (simple / borderline / too-complex) with
per-metric reasons + actionable advice. Exit code 0/1/2 so callers can branch.

Usage: python evaluate_icon.py --mask icon.mask.txt [--json]
"""
import sys, os, json, argparse
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from maskio import (load_mask, count_on, dims, connected_components, hole_count,
                    perimeter, min_feature_width, bounding_box, pyramid_layers)

# Target bands (single source of truth; documented in reference/metrics.md)
BANDS = dict(
    fill_lo=0.28, fill_hi=0.78,
    largest_cc_warn=0.90, largest_cc_fail=0.75,
    holes_warn=1,
    min_width_warn=3, min_width_fail=2,
    spikiness_warn=40.0, spikiness_fail=70.0,
    aspect_lo=0.45, aspect_hi=2.2,
    stack_warn=3, stack_fail=2,
    capacity_fail=2,
)


def evaluate(grid):
    h, w = dims(grid)
    on = count_on(grid)
    area = h * w
    comps = connected_components(grid)
    largest = len(comps[0]) / on if on else 0
    holes = hole_count(grid)
    p = perimeter(grid)
    spike = (p * p / on) if on else 999
    mfw = min_feature_width(grid)
    bb = bounding_box(grid)
    aspect = ((bb[2]-bb[0]+1) / (bb[3]-bb[1]+1)) if bb else 0
    fill = on / area if area else 0
    # stackability via the same pyramid sim mask_to_layout uses
    base = {(x, y) for y in range(h) for x in range(w) if grid[y][x]}
    layers = pyramid_layers(base)
    n_layers = len(layers)
    total_cells = sum(len(L) for L in layers)
    capacity = total_cells // 3

    m = dict(grid=f"{w}x{h}", on_cells=on, fill_ratio=round(fill, 3),
             components=len(comps), largest_cc=round(largest, 3), holes=holes,
             min_feature_width=mfw, spikiness=round(spike, 1), aspect=round(aspect, 2),
             stack_layers=n_layers, pyramid_cells=total_cells, capacity=capacity)

    reasons = []; warns = 0; fails = 0
    def warn(c): nonlocal warns; warns += 1; reasons.append("⚠ " + c)
    def fail(c): nonlocal fails; fails += 1; reasons.append("✗ " + c)

    if largest < BANDS["largest_cc_fail"]:
        fail(f"shape rời rạc ({len(comps)} mảnh, lớn nhất {largest:.0%}) — chọn icon liền khối")
    elif largest < BANDS["largest_cc_warn"]:
        warn(f"có {len(comps)} mảnh tách — nên dùng icon 1 khối")
    if n_layers < BANDS["stack_fail"]:
        fail(f"stackability {n_layers} layer (<2) — quá mỏng, không xếp tầng được; chọn icon đậm/đặc hơn")
    elif n_layers < BANDS["stack_warn"]:
        warn(f"chỉ {n_layers} layer — layout nông; tăng --grid hoặc icon dày hơn")
    if capacity < BANDS["capacity_fail"]:
        fail(f"capacity {capacity} (<2 type) — quá nhỏ; tăng --grid")
    if mfw < BANDS["min_width_fail"] and len(comps) > 1:
        fail(f"nét quá mảnh (width≈{mfw}) + nhiều nhánh — tô đầy/chọn icon đặc")
    elif mfw < BANDS["min_width_warn"]:
        warn(f"nét mảnh (width≈{mfw}) — có thể mất chi tiết khi lên tầng")
    if not (BANDS["fill_lo"] <= fill <= BANDS["fill_hi"]):
        warn(f"fill_ratio {fill:.0%} ngoài [{BANDS['fill_lo']:.0%},{BANDS['fill_hi']:.0%}] — outline/quá đặc")
    if holes > BANDS["holes_warn"]:
        warn(f"{holes} lỗ trong shape — nhiều chi tiết")
    if spike >= BANDS["spikiness_fail"]:
        fail(f"viền quá gai (spikiness {spike:.0f}) — icon quá chi tiết")
    elif spike >= BANDS["spikiness_warn"]:
        warn(f"viền gai (spikiness {spike:.0f})")
    if not (BANDS["aspect_lo"] <= aspect <= BANDS["aspect_hi"]):
        warn(f"tỉ lệ {aspect:.2f} hơi lệch")

    if fails:
        verdict = "too-complex"
    elif warns >= 2:
        verdict = "borderline"
    else:
        verdict = "simple"
    return verdict, m, reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mask", required=True)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    grid = load_mask(a.mask)
    verdict, m, reasons = evaluate(grid)
    if a.json:
        print(json.dumps({"verdict": verdict, "metrics": m, "reasons": reasons}, ensure_ascii=False))
    else:
        print(f"VERDICT: {verdict.upper()}")
        print(f"  {m}")
        for r in reasons:
            print(f"  {r}")
        if verdict == "simple" and not reasons:
            print("  ✓ tất cả metrics trong ngưỡng tốt")
    sys.exit({"simple": 0, "borderline": 1, "too-complex": 2}[verdict])


if __name__ == "__main__":
    main()
