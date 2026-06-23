"""Engine-parity guard for the tile-puzzle plugin.

Plugins cannot share one engine via a path variable (ARCHITECTURE.md §6: no ${CLAUDE_PLUGIN_ROOT}
for skills; ${CLAUDE_SKILL_DIR} is the skill's own subdir). So each skill ships its own engine copy
(P4: accept duplication, guard against drift). This test fails loudly if the two copies diverge —
run it in CI and before `claude plugin validate`.

Usage:  python tile-puzzle/tests/check_engine_parity.py
"""
import hashlib, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
A = os.path.join(ROOT, "skills", "gen-layout", "engine")
B = os.path.join(ROOT, "skills", "tile-level-design", "engine")

# files the two skills share verbatim (tld also ships count_solutions / tile_mcp_server / verify_smart_fast)
SHARED = [
    "tile_level_simulator.py", "verify_smart_v3.py", "solve_path.py",
    "tile_logger.py", "tile_metadata.py", "tile_api.py", "scoring_weights.json",
]

def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()

bad = []
for f in SHARED:
    pa, pb = os.path.join(A, f), os.path.join(B, f)
    if not (os.path.exists(pa) and os.path.exists(pb)):
        bad.append(f"MISSING {f}")
    elif md5(pa) != md5(pb):
        bad.append(f"DRIFT   {f}")

if bad:
    print("ENGINE PARITY FAIL — the two skills' engine copies diverged:")
    for x in bad:
        print("  ", x)
    print("Fix: re-sync so both engine/ dirs are byte-identical.")
    sys.exit(1)
print(f"engine parity OK — {len(SHARED)} files byte-identical across both skills")
