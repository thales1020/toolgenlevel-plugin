"""Render a mask (or layout) to a PNG so Claude can VISUALLY review shape fidelity.

Pure stdlib (zlib + struct) PNG encoder — no Pillow. The deterministic code can't
judge "does this look like a leaf?"; rendering to PNG lets Claude (vision) review
the silhouette semantically as a validation step.

Usage:
  python render_png.py --mask icon.mask.txt --out icon.png [--cell 16]
  python render_png.py --layout NewLayout_icon.json --out icon.png   # base-layer silhouette
"""
import sys, os, struct, zlib, argparse, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from maskio import load_mask, dims


def _png(width, height, rgb_rows):
    """rgb_rows: list of bytes objects, each = width*3 bytes (RGB)."""
    def chunk(typ, data):
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
    raw = b"".join(b"\x00" + row for row in rgb_rows)  # filter byte 0 per scanline
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    idat = zlib.compress(raw, 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def mask_to_png(grid, out, cell=16, fg=(53, 187, 106), bg=(245, 250, 253), grid_line=(225, 235, 230)):
    h, w = dims(grid)
    W, H = w * cell, h * cell
    rows = []
    for y in range(H):
        gy = y // cell
        row = bytearray()
        for x in range(W):
            gx = x // cell
            on = grid[gy][gx]
            # thin grid lines for readability
            edge = (x % cell == 0) or (y % cell == 0)
            if on:
                col = fg
            elif edge:
                col = grid_line
            else:
                col = bg
            row += bytes(col)
        rows.append(bytes(row))
    with open(out, "wb") as f:
        f.write(_png(W, H, rows))
    return W, H


LAYER_RGB = [(53, 187, 106), (47, 159, 208), (224, 169, 58), (208, 106, 106),
             (142, 106, 208), (70, 207, 124), (127, 140, 154), (192, 86, 58),
             (58, 120, 192), (208, 92, 168), (120, 192, 58), (86, 86, 86)]


def _layer_color(L):
    """Distinct colour per layer. Beyond len(LAYER_RGB) layers, darken each wrap
    so e.g. L0 and L12 read differently instead of rendering identically."""
    base = LAYER_RGB[L % len(LAYER_RGB)]
    wrap = L // len(LAYER_RGB)
    if wrap == 0:
        return base
    factor = max(0.4, 1.0 - 0.25 * wrap)  # darken 25% per wrap, floor at 0.4
    return tuple(int(c * factor) for c in base)


def layout_to_png(path, out, ppu=22):
    """Render the FULL stacked layout by true coords (all layers, colour per layer,
    higher layers inset + drawn on top) — shows the real shape, not a checkerboard."""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    cells = []  # (layer, x, y)
    for ly in d["layers"]:
        for s in ly["stones"]:
            cells.append((ly["index"], float(s["x"]), float(s["y"])))
    if not cells:
        # empty layout: render a tiny blank image instead of crashing on min()/max()
        print(f"WARN empty layout (no cells) in {path}; rendering blank image")
        bg = (245, 250, 253)
        W = H = ppu
        rgb_rows = [b"".join(bytes(bg) for _ in range(W)) for _ in range(H)]
        with open(out, "wb") as f:
            f.write(_png(W, H, rgb_rows))
        return W, H
    xs = [c[1] for c in cells]; ys = [c[2] for c in cells]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    pad = ppu
    W = int(round((maxx - minx) * ppu)) + ppu + pad * 2
    H = int(round((maxy - miny) * ppu)) + ppu + pad * 2
    bg = (245, 250, 253)
    canvas = [[bg for _ in range(W)] for _ in range(H)]
    side = ppu - 2
    for (L, x, y) in sorted(cells, key=lambda c: c[0]):  # base first, top last
        px = int(round((x - minx) * ppu)) + pad
        py = int(round((maxy - y) * ppu)) + pad   # flip y
        # higher layers slightly smaller so stacking reads; clamp so deep layers
        # keep a minimum visible size (never zero/negative width)
        inset = min(L, (side - 2) // 2)
        col = _layer_color(L)
        for yy in range(py + inset, py + side - inset):
            if 0 <= yy < H:
                row = canvas[yy]
                for xx in range(px + inset, px + side - inset):
                    if 0 <= xx < W:
                        row[xx] = col
    rgb_rows = [b"".join(bytes(px) for px in row) for row in canvas]
    with open(out, "wb") as f:
        f.write(_png(W, H, rgb_rows))
    return W, H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mask")
    ap.add_argument("--layout")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cell", type=int, default=16)
    a = ap.parse_args()
    if a.mask:
        W, H = mask_to_png(load_mask(a.mask), a.out, a.cell)
    else:
        W, H = layout_to_png(a.layout, a.out, ppu=max(14, a.cell + 6))
    print(f"SAVED {a.out}  {W}x{H}px")


if __name__ == "__main__":
    main()
