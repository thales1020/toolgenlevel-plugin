"""POST-TILE overlay: flag normal tiles with `m: true` on a COMPLETE level.

The three special-cell types each have their OWN correct step (do NOT mix them into gen):
  - STACK (straight pile)        = GEOMETRY  -> gen-layout/scripts/add_stacks.py   (BEFORE tiles)
  - BONUS 1001 / MISSION 1002    = reserved non-match-3 slot -> scripts/reserve_special.py (AT tiles)
  - MARK (`m: true`)             = a flag on an existing NORMAL match-3 tile -> THIS tool (AFTER tiles)

`m: true` (seen on early reference levels) marks a normal playable tile — it changes nothing about
geometry or match-3 balance, just adds the flag — so it is a safe post-tile overlay. The engine
ignores it. This tool preserves every other field.

Usage:
  python add_special_cells.py <level.json> [--out out.json] [--mark N] [--seed 1]
"""
import sys, os, json, argparse, random


def main():
    ap = argparse.ArgumentParser(description="Flag N normal tiles with m:true (post-tile overlay).")
    ap.add_argument("level")
    ap.add_argument("--out", default="")
    ap.add_argument("--mark", type=int, default=0, help="flag N normal (non-special) stones with m:true")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()

    data = json.load(open(a.level, encoding="utf-8"))
    rng = random.Random(a.seed)
    # eligible = normal match-3 tiles (not the 100x specials, not already marked)
    pool = [s for ly in data["layers"] for s in ly.get("stones", [])
            if not s.get("m") and int(s.get("i", 0)) < 1000]
    n = min(a.mark, len(pool))
    for s in rng.sample(pool, n):
        s["m"] = True

    out = a.out or a.level.replace(".json", "_marked.json")
    json.dump(data, open(out, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    print(f"-> {out}")
    print(f"   marked {n} normal tiles with m:true (geometry + match-3 balance unchanged)")


if __name__ == "__main__":
    main()
