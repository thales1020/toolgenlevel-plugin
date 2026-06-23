---
name: Cascade Assignment for deep uniform layouts
description: When layout has uniform layers where only top layer is pickable (like L21), place same easy type vertically in stacks so picking reveals cascade triples below.
type: feedback
originSessionId: 5bf952b0-04ed-42f3-9813-354182a6e8fb
---
**Cascade Assignment** — a tile placement strategy for deep uniform layouts where standard priority assignment fails.

**Problem**: Layouts like L21 (5 layers, 13-14 cells each) have only the top layer (L4) pickable at start. L0-L3 = 0 pickable cells, all 100% covered. Placing easy types on lower layers is invisible to the player — defeats "easy top" intent.

**Solution**: Place the SAME easy type vertically through a stack:
```
L4: [A] ← pick this
L3: [A] ← revealed → pick next  
L2: [A] ← revealed → cascade clear!
```
Player experiences: cascade — each pick reveals more of the same type, feels "easy" despite deep layout.

**L21 specifics**:
- 66 cells, 5 layers (uniform 13-14), capacity=22
- 14 pickable cells (all on L4, 21%)
- 26 cover100 cells (42%)
- 11 cascade chains found (7 of them 5-deep at y=-2.0)
- Max buried depth: 8 blockers

**Three assignment approaches compared**:
| Approach | Best for | Instant triples | Experience |
|---|---|---|---|
| Random | Any | Uncontrolled | Luck-based |
| Priority (cover100-aware) | Layouts with spread pickable cells (L20) | ≥2 guaranteed | See triples immediately |
| Cascade | Deep uniform layouts (L21) | ≥2 + cascade reveals | Pick → reveal → cascade clear |

**Why:** User pointed out that L21's uniform layers make priority assignment ineffective — only L4 is visible. Cascade solves this by exploiting vertical stacks so clearing top tiles reveals matching tiles below.

**How to apply:** When layout has uniform deep layers with few pickable cells, analyze vertical stacks first (`find_cascade_chain`). Assign same easy type to cells in each chain. Use `find_hybrid_cascade_L21.py` as template.

**Script**: `find_hybrid_cascade_L21.py` — finds cascade chains, assigns easy types vertically, filters v3 + greedy fail + score.
