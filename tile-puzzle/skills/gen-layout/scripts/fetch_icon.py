"""Fetch an icon SVG from the free Iconify API (no auth, no limit).

Usage:
  python fetch_icon.py mdi:heart --out heart.svg
  python fetch_icon.py mdi:heart            # prints SVG to stdout

Icon ids: browse https://icon-sets.iconify.design  (prefix:name, e.g. mdi:heart,
ph:star-fill, tabler:diamond). Icons are open-source — keep the per-set license/
attribution. Needs network (local only; not the web sandbox).
"""
import sys, os, argparse, urllib.request, urllib.error

API = "https://api.iconify.design"


def fetch_svg(icon_id, height=240):
    if ":" not in icon_id:
        raise SystemExit(f"icon id must be 'prefix:name' (got {icon_id!r})")
    prefix, name = icon_id.split(":", 1)
    url = f"{API}/{prefix}/{name}.svg?height={height}"
    req = urllib.request.Request(url, headers={"User-Agent": "tile-layout-gen"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            svg = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"icon not found ({e.code}): {icon_id}")
    except urllib.error.URLError as e:
        raise SystemExit(f"network error for {icon_id}: {e.reason}")
    if "<svg" not in svg or "404" in svg[:40]:
        raise SystemExit(f"icon not found: {icon_id} (check prefix:name on icon-sets.iconify.design)")
    return svg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("icon")
    ap.add_argument("--out")
    ap.add_argument("--height", type=int, default=240)
    a = ap.parse_args()
    svg = fetch_svg(a.icon, a.height)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"SAVED {a.out}  ({len(svg)} bytes)  icon={a.icon}")
    else:
        sys.stdout.write(svg)


if __name__ == "__main__":
    main()
