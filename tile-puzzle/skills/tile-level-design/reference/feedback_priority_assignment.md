---
name: Priority-based tile assignment for easy-top levels
description: When assigning easy types to top layers, place them on pickable/visible cells first (tier1), NOT on cover100 cells — improves perceived "easy" feeling
type: feedback
originSessionId: 9cb29a82-5617-4dd8-9f97-2bb165e50048
---
When building hybrid easy-top + trap-bottom levels, do NOT randomly shuffle easy types across all top-layer cells. Cells in top layers have different visibility:

- **Tier 1** (0 blockers, pickable): player sees and can pick immediately — PUT EASY TYPES HERE FIRST
- **Tier 2** (1-2 blockers, partial): revealed after 1-2 picks — good for easy types
- **Tier 3** (3+ blockers, cover100): completely hidden — wasted if easy types placed here

**Why:** User pointed out that placing easy triples on cover100 cells is meaningless — player can't see or pick them, so it doesn't create the "easy" feeling. Only pickable/visible cells matter for perceived difficulty.

**How to apply:**
1. Precompute `block_count[i]` for each cell (how many higher-layer cells overlap it)
2. Classify top-layer cells: tier1 (bc=0), tier2 (bc=1-2), tier3 (bc≥3)
3. Build `top_priority_order = tier1 + tier2 + tier3`
4. Front-load easy pool: put 3-4 copies of 2-3 types at the start of the pool
5. Assign pool[i] → top_priority_order[i] — ensures easy types land on visible cells
6. Filter: require `instant_triples ≥ 2` in tier1 (pickable cells have ≥ 2 complete triples)

**Template:** `find_hybrid_priority_v2.py`

**L20 stats:** 36 top cells = 13 tier1 + 11 tier2 + 12 tier3. With priority assignment, 3 instant triples visible at game start.
