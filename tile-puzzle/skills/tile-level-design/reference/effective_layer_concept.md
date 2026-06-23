---
name: effective_layer concept and scoring overhaul
description: "effective_layer = #higher_physical_layers_with_overlap + 1. Used in: 2-window strip + cover100. layout still uses physical layer. Same-type subtract still uses physical layer (intentional design)."
type: reference
originSessionId: 5bf952b0-04ed-42f3-9813-354182a6e8fb
---
**`effective_layer`** — new "depth" measure that better reflects player-perceived difficulty than physical `layer_idx`.

**Formula**: `effective_layer = (#distinct_higher_physical_layers_with_overlapping_active_cell) + 1`

| Tile state | effective_layer |
|---|---|
| Top, no overlap above | 1 |
| 1 layer above overlaps | 2 |
| N layers above overlap | N+1 |
| Fully buried (max possible) | max_layer - my_layer + 1 |

**Recomputed each iteration** during strip (active set shrinks).

## Application matrix

| Component | Uses |
|---|---|
| **layout score** | physical `layer_idx` (full board, unchanged) |
| **2-layer window strip** | **effective_layer** (`max_eff - min_eff <= 2`) |
| **same-type subtract** in effective scores | **physical layer** (intentional, see below) |
| **cover100** | **effective_layer** (cells at `max(eff_layers)`) |
| **inter_group / intra_group** | uses effective scores (which use physical for subtract) |

## Why same-type subtract uses PHYSICAL layer (not effective)

**Original logic**: subtract 1 if ANY same-type at physical layer above overlaps.

**Tested alternative** (subtract -N where N = count of same-type above): would let vertical stacks of 3 same-type tiles fully strip out. But this is WRONG because:

> Tile bị che 100% = invisible cho player → player KHÔNG biết tile thứ 3 ở đâu → không phải "easy triple" theo perspective player.

So keep `-1` (any same-type above):
- Stack of 3 same-type vertical: only top 2 get effective ≤ 0 → strip can't form triple → STAYS in inter/intra/cover100
- This is correct: hidden cascade stacks ARE harder for player than visible triples
- **Cascade Strategy** exploits this: place easy types vertical → strip doesn't reduce score, but player still feels "easy" via reveal cascade

## Why cover100 uses effective_layer (not geometric 4-corner)

**Old**: cover100 = #cells with `coverage == 4` (geometric 4-corner check).

**New**: cover100 = #cells where `effective_layer == max(effective_layers in active)` AND max > 1.

Reasons:
- Geometric 4-corner depends on tile shape (1×1 squares with half-grid offsets) → fragile to layout design
- effective_layer directly measures "how buried" → more semantic
- Active-set based: cover100 reduces as tiles cleared (same as inter/intra)

**Hệ quả**:
- Score range mở rộng đáng kể với deep layouts (max ~120 → ~200)
- Layouts nông (L60, L4) thay đổi ít

## Test edge case (vertical 3-stack same type at same x,y)

| Layer | BFS count | Same-type subtract | Effective |
|---|---|---|---|
| L4 (top) | 0 | 0 (nothing above) | **0** ≤ 0 ✓ |
| L3 (middle) | 1 | -1 | **0** ≤ 0 ✓ |
| L2 (bottom, cover100) | 2 | -1 | **1** > 0 ✗ |

Only 2 tiles have effective ≤ 0 → strip can't form triple → stack stays. **Correct behavior** per design.

## Files changed

- `tile_level_simulator.py`:
  - Added `compute_effective_layers(board, active)`
  - `_find_triple_within_2_layers(candidates, randomize, eff_layers=None)` — accepts eff_layers
  - `_compute_effective_on_active(board, active, eff_layers=None)` — eff_layers param (currently unused for subtract, kept for future)
  - `strip_easy_triples` — recomputes eff_layers each iteration
  - `compute_full_score` — eff_layers-based cover100, no more `eff_cover` field

- `difficulty_minmax_combined.csv` — re-swept with new scoring (21 minutes, 2636 rows)

## Bug history

Initial implementation had `if other_eff > my_eff` for same-type subtract, which was BACKWARDS (filtered out all valid same-type above tiles). Fixed by reverting to physical-layer iteration without the eff_layer comparison.
