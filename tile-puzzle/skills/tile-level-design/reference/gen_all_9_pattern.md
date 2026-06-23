---
name: gen_all_9.py — fastest way to generate all 9 patterns
description: Single-script parallel execution: 7 external scripts via subprocess.Popen + 2 inline patterns (P2/P8). Saves to all_9_boards.json in ~20 seconds.
type: reference
originSessionId: 5bf952b0-04ed-42f3-9813-354182a6e8fb
---
**`gen_all_9.py`** — generates all 9 pattern levels in parallel, ~20 seconds total.

**Implementation pattern**:
1. **External scripts** (subprocess.Popen): P1, P3, P4, P5, P6, P7, P9 — launched non-blocking, run on separate Python processes
2. **Inline functions** (gen_p2, gen_p8): P2 (Top Easy) and P8 (80% Fail) run inline in main process — these are fastest patterns
3. **Wait + collect**: `p.wait()` for all subprocesses, then read all candidate JSONs
4. **Single output**: aggregate all 9 boards into `all_9_boards.json` for batch loading + play

**Why this works**:
- Python GIL doesn't matter because subprocesses are separate processes
- 7 parallel + 2 sequential inline = ~20s total (longest single script + overhead)
- Sequential approach took ~30 minutes; parallel cuts to ~20s = **90x speedup**

**Usage**:
```bash
python gen_all_9.py
# → all_9_boards.json (9 verified levels)
```

**When to use**: User wants demo of all patterns, or batch generation for a level pack. Don't use for single-pattern requests (waste of resources).

**How to apply**: When user asks "tạo 9 levels" / "demo all patterns" / "level pack" → use `gen_all_9.py` directly. To customize seeds, edit the SCRIPTS list at top.

**Saved levels in `all_9_boards.json`**:
1. P1 Trap An (`find_l20_17.py`)
2. P2 Top Easy (inline gen_p2)
3. P3 Hybrid Random (`find_hybrid_custom_fast.py`)
4. P4 Hybrid Priority (`find_hybrid_priority_v2.py`)
5. P5 Cascade L21 (`find_hybrid_cascade_L21.py`)
6. P6 90% Fail (`find_trap_70_90.py`)
7. P7 Guided Trap (`find_guided_trap_L21.py`)
8. P8 80% Fail (inline gen_p8)
9. P9 Clear 50% (`find_clear50_trap.py` on L74)
