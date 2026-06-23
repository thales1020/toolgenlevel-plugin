---
name: Tile level difficulty design workflow
description: Approved approach for finding levels that meet "score X-Y + top N layers easy + unsolvable/N% fail" style constraints
type: feedback
originSessionId: 5bf952b0-04ed-42f3-9813-354182a6e8fb
---
User's typical ask: "tạo level score A-B với N types, top K layer phải dễ, ..."

**Workflow**:
1. Write a dedicated `find_*.py` script per constraint style. 8 parallel workers by random seed.
2. Per candidate: generate tiles, filter by score range + type count, measure the target metric, v3 solvability check.
3. Save first match to `*_candidate.json`, kill other workers, play via MCP.

**Metrics that worked** (ranked by usefulness):
- **2-adjacent-layer window triple metric** (BEST for "layer dễ" asks): for top N layers, slide a 2-layer window; a type is "easy" if it has ≥3 copies within any window; measure fraction of top-N tiles belonging to easy types. Matches how players actually see triples — they look at top layer + partially exposed layer below and spot triples. Threshold: `window_frac ≥ 0.85`. This is the approved metric when user says "3 layer đầu tiên dễ" / "layer dễ".
- **Top N easy via full distribution**: count distinct types in top N layers, count types with ≥3 copies in top N as a whole. OK but too strict when top N has only 18 cells (e.g. 5-6 layer layouts) — math forces max 6 types. Use only for 3-4 layer layouts where top N is wide.
- **Tray pressure profile along v3 path**: early_avg vs late_avg tray size. OK for "2-phase" ask but v3 often makes profile flat (atomic triples clear cleanly).
- **Deadlock depth via beam search exhaustion**: for "unsolvable" / "clear X% before deadlock". Requires v3 solver with exhaustion proof.

**Metrics that failed** (don't bother):
- Random / greedy playout survival rate → too harsh, v3 atomic-triple path is nothing like a random player.
- Sub-board isolation solve (extract top N as standalone) → top N rarely has tile counts divisible by 3, so isolation is usually unsolvable even when top N is empirically easy.
- Tray size via max (instead of avg) → v3 almost always packs to 6 at some point, so early_max is rarely low.

**Relaxation pattern when threshold too strict**:
- Score range first (e.g. 60-80 → 50-70 if nothing hits).
- Then top N thresholds (e.g. max_types 5 → 8, triple_types 3 → 4, window_frac 0.90 → 0.85).
- Never relax the user's explicit tile count range without telling them.
- For window_frac, empirical ceiling with score 60+ and types 10+ is ~0.93. Start at 0.85, tighten later.

**Layout pool selection by constraint**:
- "Top N layers easy" with strict thresholds → use 4-layer layouts only (L86, L70, L18, L13, etc.) where top 3 covers ~80% of cells, giving math room for many types.
- Top 3 on 5-6 layer layouts (L50, L115) has only 18 cells → hard cap of 6 triple-ready types.
- 3-layer layouts give top 3 = 100% of cells but may lack depth for high scores.

**Parallelism**: 8 workers via `for seed in 1 11 23 47 101 239 991 1001; do python find_x.py $seed > log_$seed.log 2>&1 & done`. Seeds chosen to spread RNG without collisions. Kill via `wmic process where "CommandLine like '%%find_x%%'" delete`.

**Why:** After many experiments across this project, these are the approaches that actually produce candidates the user accepts. The failed metrics looked sensible on paper but consistently misfired against v3's atomic-triple behavior.

**How to apply:** When user asks for a new level-design constraint, start from this playbook. Pick the metric from the "worked" list closest to their ask. Only invent a new metric if none of the proven ones fit.
