---
name: Layout strategy mapping for 5 design patterns
description: Which tile assignment strategy (Random/Priority/Cascade) to use per layout, combined with 5 level design patterns. Reference file layout_strategy_analysis.csv.
type: reference
originSessionId: 5bf952b0-04ed-42f3-9813-354182a6e8fb
---
**Layout strategy analysis**: `layout_strategy_analysis.csv` classifies all 117 layouts into 3 tile assignment strategies based on structural analysis (pickable cells, cover100, vertical stacks, layer uniformity).

## 3 Assignment Strategies × 5 Design Patterns

When user requests a level, combine the **design pattern** (what kind of level) with the **assignment strategy** (how to place tiles on this layout):

### Strategy selection per layout

| Strategy | # Layouts | Criteria | Key layouts |
|---|---|---|---|
| **Cascade** | 19 | Top-only pickable + uniform layers + stacks ≥3 deep | L21, L98, L46, L14, L54, L15, L52, L77 |
| **Priority** | 74 | Pickable across 2+ layers | L20, L25, L50, L86, L70, L107, L55, L80 |
| **Random** | 24 | Single pickable layer, no useful stacks | L10, L18, L38, L41, L49, L73, L79, L93 |

### How strategies combine with 5 patterns

| Pattern | Random layout | Priority layout | Cascade layout |
|---|---|---|---|
| **1. Trap ẩn** | TEEngine + greedy fail (standard) | TEEngine + greedy fail (standard) | TEEngine + greedy fail (standard) |
| **2. Top N dễ** | TEEngine + window metric | TEEngine + window metric | TEEngine may fail; consider cascade assignment |
| **3. Easy top + trap bottom** | Custom random pool per half | Custom + easy on pickable only | Custom + easy in vertical stacks |
| **4. 90% fail** | TEEngine + greedy fail (standard) | TEEngine + greedy fail (standard) | TEEngine + greedy fail (standard) |
| **5. Clear 50% rồi bí** | Custom random + avg_cleared | Custom priority + avg_cleared | Custom cascade + avg_cleared |

**Key rules**:
- Patterns 1 & 4 (pure trap): strategy doesn't matter much — TEEngine handles it. All 3 strategies work.
- Patterns 2, 3, 5 (easy top involved): strategy MATTERS. Must check `layout_strategy_analysis.csv` first.
- For **Priority** layouts: easy types go on pickable cells only, avoid cover100.
- For **Cascade** layouts: easy types placed in vertical stacks for cascade reveals.
- For **Random** layouts: no structural advantage for targeted placement; random pool shuffle is fine.

## Quick lookup before generating

1. User gives layout ID (e.g., L21)
2. Check `layout_strategy_analysis.csv` → get `recommended_strategy`
3. If pattern needs "easy top" (patterns 2, 3, 5):
   - Cascade → use `find_hybrid_cascade_L21.py` template
   - Priority → use `find_hybrid_fast.py` with cover100-aware placement
   - Random → use `find_hybrid_fast.py` with standard random pool
4. If pattern is pure trap (patterns 1, 4):
   - Use `find_trap_fast.py` regardless of strategy

## Layout highlights for each strategy

**Best Cascade layouts** (deepest stacks):
- L46: 7-deep stacks, 69 cells, 7 layers
- L21: 5-deep stacks, 66 cells, 5 uniform layers
- L98: 5-deep stacks × 14, 66 cells, 10 layers
- L14/L54: 40 stacks × 3-deep, 120 cells (large)

**Best Priority layouts** (most pickable spread):
- L70: pickable across 4 layers, 72 cells
- L119: pickable across 4 layers, 114 cells
- L117: pickable across 4 layers, 66 cells
- L20: pickable across 2 layers, 72 cells (proven reference)

**Random layouts** (simple structure):
- L38/L41: 78 cells, 24-26 pickable (30-33%), single layer
- L4: 63 cells, 26 pickable (41%), 2 layers
- L79/L93: 99 cells, large but flat structure
