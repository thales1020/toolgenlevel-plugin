"""Export a generated level to the EXACT game LEVEL format (byte-shape-identical to the reference
Mission files). Our generators emit a `metadata` block and omit the game wrapper fields; the game
level format (reverse-engineered from 45 reference files) is:

  {"group":<int>, "tiles":"", "layers":[...], "stacks":[...], "bg":<str>, "bgm":<str>, "sl":2, "dif":1}

No `metadata`. Constants `sl=2` and `dif=1` are the same in ALL 45 reference files. `bg`/`bgm` default
to "" (a valid value present in the reference); override with --bg/--bgm. `group` is preserved (or
--group). Stone fields (i,x,y,s,m) and stacks {x,y,d} are already game-identical and copied as-is.

Run this as the FINAL pipeline step on a complete level (after tiles + any stack/mission/mark cells).

Usage:
  python export_game_format.py <level.json> [--out out.json] [--group N] [--bg ""] [--bgm ""]
"""
import json, os, argparse


def to_game_format(data, group=None, bg="", bgm=""):
    """Return the level as the exact game dict (key order matches the reference). Drops `metadata`."""
    return {
        "group": int(group) if group is not None else data.get("group", 1),
        "tiles": data.get("tiles", ""),
        "layers": data["layers"],
        "stacks": data.get("stacks", []),
        "bg": bg,
        "bgm": bgm,
        "sl": 2,
        "dif": 1,
    }


def main():
    ap = argparse.ArgumentParser(description="Export a level to the exact game format (drops metadata).")
    ap.add_argument("level")
    ap.add_argument("--out", default="")
    ap.add_argument("--group", type=int, default=None, help="override group id (else preserved)")
    ap.add_argument("--bg", default="", help='background asset (default "")')
    ap.add_argument("--bgm", default="", help='bgm asset (default "")')
    a = ap.parse_args()

    data = json.load(open(a.level, encoding="utf-8"))
    game = to_game_format(data, group=a.group, bg=a.bg, bgm=a.bgm)
    out = a.out or a.level.replace(".json", "_game.json")
    json.dump(game, open(out, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    print(f"-> {out}")
    print(f"   game format: keys={list(game)}  (metadata dropped; sl=2 dif=1 bg={game['bg']!r} bgm={game['bgm']!r})")
    print(f"   {sum(len(ly.get('stones', [])) for ly in game['layers'])} stones, {len(game['stacks'])} stacks")


if __name__ == "__main__":
    main()
