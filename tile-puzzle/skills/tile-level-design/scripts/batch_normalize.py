"""Batch normalize: compute difficulty + inject metadata + drop 'dif' field. Matches L60 format."""
import sys, os, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from analyze_level import compute_metadata

# Levels folder is an OUTPUT location (lives wherever you run, not in the skill).
# Pass as argv[1], else default to ./levels relative to current working dir.
FOLDER = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.abspath("levels")
LEVELS = [f"NewLayout_L{n}.json" for n in range(3, 21)]

results = []
for fname in LEVELS:
    path = os.path.join(FOLDER, fname)
    t0 = time.time()
    try:
        metadata, data = compute_metadata(path)
    except Exception as e:
        print(f"{fname}: ERROR {e}")
        continue
    elapsed = time.time() - t0

    # Drop legacy fields, add metadata
    data.pop("dif", None)
    data["metadata"] = metadata
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)

    c = metadata["score_components"]
    results.append((
        fname.replace("NewLayout_", "").replace(".json", ""),
        metadata["n_layers"], metadata["total_tiles"], metadata["n_types"],
        metadata["difficulty"],
        c["layout"], c["inter_group"], c["intra_group"],
        c["cover100"], c["pickable_diversity"],
        elapsed,
    ))
    print(f"  {fname:25s} -> diff={metadata['difficulty']:6.2f}  ({elapsed:.1f}s)")

print()
print(f"{'Layout':>8} {'Lyr':>4} {'Cells':>5} {'Typ':>4} {'Difficulty':>10} | {'layout':>7} {'inter':>7} {'intra':>7} {'cv100':>6} {'pkdv':>5}")
print("-" * 90)
for r in results:
    print(f"{r[0]:>8} {r[1]:>4} {r[2]:>5} {r[3]:>4} {r[4]:>10.2f} | {r[5]:>7.2f} {r[6]:>7.2f} {r[7]:>7.2f} {r[8]:>6} {r[9]:>5}")
