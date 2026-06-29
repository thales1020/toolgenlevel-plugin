"""POST-TILE overlay: flag normal tiles with `m: true` (MYSTERY tile) on a COMPLETE level.

The special-cell types each have their OWN correct step (do NOT mix them into gen):
  - STACK (straight pile)        = GEOMETRY  -> gen-layout/scripts/add_stacks.py   (BEFORE tiles)
  - BONUS 1001 / MISSION 1002    = reserved non-match-3 slot -> scripts/reserve_special.py (AT tiles)
  - MYSTERY (`m: true`)          = a flag on an existing NORMAL match-3 tile -> THIS tool (AFTER tiles)

MYSTERY tile (`m: true`, confirmed from the L*M reference set): a normal playable match-3 tile that is
just FACE-DOWN to the player — its colour is FIXED at design time, only HIDDEN visually until revealed.
It participates in match-3 exactly like any tile (every reference L*M board stays ÷3 WITH the mystery
tiles counted), so it changes NOTHING about geometry, match-3 balance, or solvability — it only adds
the `m` flag. Safe to add LAST. Reference levels carry 3-5 mystery tiles each (the default here).
The engine ignores the flag for solving. This tool preserves every other field.

Usage:
  python add_special_cells.py <level.json> [--out out.json] [--mystery N | --mark N] [--seed 1]
  # omit the count -> a random 3-5 mystery tiles (the reference convention).
"""
import sys, os, json, argparse, random


def main():
    ap = argparse.ArgumentParser(description="Flag N normal tiles as MYSTERY (m:true) — post-tile overlay.")
    ap.add_argument("level")
    ap.add_argument("--out", default="")
    # --mystery is the canonical name; --mark is kept as a backward-compatible alias (same dest).
    ap.add_argument("--mystery", "--mark", dest="mystery", type=int, default=None,
                    help="flag N normal (non-special) stones with m:true; default = random 3-5")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()

    data = json.load(open(a.level, encoding="utf-8"))
    rng = random.Random(a.seed)
    # default to the reference convention of 3-5 mystery tiles when no count is given
    want = a.mystery if a.mystery is not None else rng.randint(3, 5)
    # eligible = normal match-3 tiles (not the 1001/1002 specials, not already mystery)
    pool = [s for ly in data["layers"] for s in ly.get("stones", [])
            if not s.get("m") and int(s.get("i", 0)) < 1000]
    n = min(want, len(pool))
    for s in rng.sample(pool, n):
        s["m"] = True

    out = a.out or a.level.replace(".json", "_mystery.json")
    json.dump(data, open(out, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    print(f"-> {out}")
    print(f"   flagged {n} mystery tiles (m:true) — geometry + match-3 balance + solvability unchanged")


if __name__ == "__main__":
    main()
