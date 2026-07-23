"""POST-TILE overlay: flag normal tiles as MYSTERY (`o:[0]`) on a COMPLETE level.

The special-cell types each have their OWN correct step (do NOT mix them into gen):
  - STACK (straight pile)        = GEOMETRY  -> gen-layout/scripts/add_stacks.py   (BEFORE tiles)
  - BONUS 1001 / MISSION 1002    = reserved non-match-3 slot -> scripts/reserve_special.py (AT tiles)
  - CLOUD (`o:[1]`)              = normal tile under a cover, bottom-layer symmetric -> add_cloud.py (AFTER tiles)
  - MYSTERY (`o:[0]`)           = a flag on an existing NORMAL match-3 tile -> THIS tool (AFTER tiles)

MYSTERY tile: a normal playable match-3 tile that is FACE-DOWN to the player — its colour is FIXED at
design time and stays HIDDEN while on the board (even when pickable); the player picks it BLIND and only
sees its real colour once it is picked into the TRAY. It participates in match-3 exactly like any tile
(the board stays ÷3 WITH the mystery tiles counted), so it changes NOTHING about geometry, match-3
balance, or solvability — it only adds the `o:[0]` flag. Placement is RANDOM (any layer), 3-5 per level
by default. Safe to add LAST.

NEW format `o:[0]` (the `o` field: 0 = mystery, 1 = cloud). The old `m:true` marker is LEGACY — this
tool still SKIPS stones that already carry `m` (so it won't double-flag old levels), but it GENERATES
the new `o:[0]`. Readers (make_play_html, diff_score) accept both. The engine ignores the flag for
solving. This tool preserves every other field.

Count (spec PHẦN 7): when --mystery is omitted, the count is CONTEXT-AWARE —
  5 mystery ALONE · 4 when the level also has Mission/Bonus (1001/1002) · 3 when it also has Cloud (o:[1]).
Placement (spec PHẦN 7 + bug #11): distributed EVENLY across layers, at most 2 per layer, and only over
layers that hold >= 1 real NORMAL tile (special-only interstitial layers are skipped — flagging needs a
normal tile). Cloud cells are never re-flagged (Cloud ∩ Mystery = ∅), so add Cloud FIRST, then Mystery.

Usage:
  python add_special_cells.py <level.json> [--out out.json] [--mystery N | --mark N] [--seed 1]
  # omit the count -> context-aware 5 / 4 / 3 (alone / +special / +cloud).
"""
import sys, os, json, argparse, random


def _is_flagged(s):
    """Already a mystery/cloud (legacy m:true or new o:[0]/o:[1])."""
    return bool(s.get("m")) or bool(s.get("o"))


def _default_count(data):
    """Context-aware default (spec PHẦN 7): +cloud -> 3, else +special -> 4, else alone -> 5.
    Cloud is the tightest constraint, so it wins when a level has both cloud and special."""
    has_cloud = any(1 in (s.get("o") or [])
                    for ly in data.get("layers", []) for s in ly.get("stones", []))
    has_special = any(int(s.get("i", 0)) >= 1000
                      for ly in data.get("layers", []) for s in ly.get("stones", []))
    if has_cloud:
        return 3
    if has_special:
        return 4
    return 5


def main():
    ap = argparse.ArgumentParser(description="Flag N normal tiles as MYSTERY (o:[0]) — post-tile overlay.")
    ap.add_argument("level")
    ap.add_argument("--out", default="")
    # --mystery is the canonical name; --mark is kept as a backward-compatible alias (same dest).
    ap.add_argument("--mystery", "--mark", dest="mystery", type=int, default=None,
                    help="flag N normal (non-special) stones as mystery (o:[0]); default = context-aware 5/4/3")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()

    data = json.load(open(a.level, encoding="utf-8"))
    rng = random.Random(a.seed)
    want = a.mystery if a.mystery is not None else _default_count(data)

    # Group eligible normal tiles by layer; only layers with >= 1 eligible tile take part (bug #11:
    # a special-only interstitial layer has no normal tile to flag, so it must NOT count as a layer).
    by_layer = {}
    for ly in data["layers"]:
        idx = ly.get("index", 0)
        elig = [s for s in ly.get("stones", [])
                if not _is_flagged(s) and int(s.get("i", 0)) < 1000]
        if elig:
            rng.shuffle(elig)
            by_layer[idx] = elig
    order = sorted(by_layer)
    rng.shuffle(order)                    # fair layer order for the round-robin

    # Round-robin one-per-layer per pass -> even distribution; cap 2 per layer.
    counts = {L: 0 for L in order}
    placed = 0
    while placed < want:
        progressed = False
        for L in order:
            if placed >= want:
                break
            if counts[L] >= 2 or counts[L] >= len(by_layer[L]):
                continue
            by_layer[L][counts[L]]["o"] = [0]   # NEW mystery marker (0 = mystery, 1 = cloud)
            counts[L] += 1
            placed += 1
            progressed = True
        if not progressed:                # every layer at cap-2 or exhausted
            break

    dist = ", ".join(f"L{L}:{c}" for L, c in sorted(counts.items()) if c)
    out = a.out or a.level.replace(".json", "_mystery.json")
    json.dump(data, open(out, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    print(f"-> {out}")
    if placed < want:
        print(f"   NOTE: wanted {want} but layout capacity (<=2/layer over {len(order)} layers) allowed {placed}")
    print(f"   flagged {placed} mystery tiles (o:[0]), <=2/layer even [{dist}] — "
          f"geometry + match-3 balance + solvability unchanged")


if __name__ == "__main__":
    main()
