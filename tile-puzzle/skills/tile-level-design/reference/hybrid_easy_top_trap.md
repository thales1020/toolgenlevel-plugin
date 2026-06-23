---
name: Hybrid easy-top + trap-bottom level design
description: Custom tile assignment pattern — top N layers pure easy (few types, many copies), bottom layers trap (many types, few copies). Bypasses TEEngine entirely.
type: feedback
originSessionId: 5bf952b0-04ed-42f3-9813-354182a6e8fb
---
**"Hybrid easy-top + trap-bottom"** — a proven custom tile assignment pattern that bypasses TEEngine.

**Core idea**: Instead of using TEEngine to generate tiles, manually assign tile IDs with a controlled distribution:
- **Top half** (e.g., top 3 of 6 layers): few types with many copies → player sees easy triples, greedy clears ~40-50% of board
- **Bottom half**: many types with few copies each → trap, greedy dies 100%

**Math for L20 (72 cells, 6 layers, 17 types)**:
- 7 types × 6 copies + 10 types × 3 copies = 72
- **6×6 variant (pure easy top)**: 6 types × 6 copies fill top 3 layers (36 cells). 1 type × 6 + 10 types × 3 fill bottom 3 (36 cells). Max score ~80.7.
- **6×4 variant (tight trap)**: 6 types × 4 copies in top (24 cells) + trap types fill remaining 12 top cells. Score up to ~83.5 but top is harder.

**Search script pattern** (`find_hybrid_custom.py`):
1. Load layout structure (cell positions only)
2. Build blocking bitmask
3. Loop: shuffle tile pool per half → assign → score → v3 check → greedy playout
4. Filter: v3 solvable + fail_rate ≥ 80% + score in range
5. Save best by (score) or (avg_cleared, score)

**Key findings**:
- TEEngine can NOT produce this distribution — custom assignment is required
- Custom assignment score range is WIDER than TEEngine (lower min, slightly higher max)
- difficulty_minmax_custom.csv captures this expanded range
- v3 solvability rate is high (~3%) for custom assignment vs ~0.2% for TEEngine with same constraints
- L20 with 17 types: only 13 pickable cells at start → max 4 instant triples (not 5)
- **Avoid placing easy triples on 100% covered tiles** — tiles that are fully blocked (cover100) are invisible to the player at the start. Placing easy triples there defeats the purpose of "easy top" because the player can't see or pick them. When assigning easy types to top layers, prefer cells that are pickable or at most partially covered, NOT cells with cover100. This makes the "easy" feeling match the player's actual experience.

**Why:** User wanted "3 layer đầu rất dễ, greedy clear dễ dàng, 3 layer còn lại trap ẩn." TEEngine's knobs (top3_easy, distance, etc.) couldn't achieve this with 17 types — too few copies per type in top layers. Custom assignment solves it by forcing the distribution.

**How to apply:** When user asks for "easy start + hard finish" or "dễ đầu khó cuối" with specific type count, use custom tile assignment instead of TEEngine. Template: `find_hybrid_custom.py`.

**Saved levels**:
- `L20_hybrid_easytop_s81.json` — 6×6, score 80.7, 100% fail, pure easy top
- `L20_hybrid_tight_s84.json` — 6×4, score 83.5, 100% fail, trap mixed in top
