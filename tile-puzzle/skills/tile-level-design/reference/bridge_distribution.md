---
name: Bridge Distribution pattern for level design
description: Use "bridge types" (6 copies spanning top-to-bottom) to connect easy top and trap bottom, so revealed tiles feel familiar. Learned from analyzing real Yellow L21 level.
type: feedback
originSessionId: 5bf952b0-04ed-42f3-9813-354182a6e8fb
---
**Bridge Distribution** — the missing piece in hybrid easy-top + trap-bottom design.

**Problem with previous approaches**: Sharp gradient creates a "wall" — player clears easy top then gets hit with completely unfamiliar trap types. Real game levels don't feel this way.

**Solution from real Yellow L21 level**: Use 3 type groups:

| Group | Copies | Placement | Role |
|---|---|---|---|
| **Easy-only** | 3x each | Only top 2 layers (L4+L3) | Clear easily, disappear |
| **Bridge** | 6x each | Spread across ALL layers (L4→L0) | Player sees them on top, recognizes when revealed below |
| **Trap-only** | 3x each | Only bottom layers (L2→L0) | Unfamiliar, hard to match |

**Yellow L21 example (18 types, 66 cells)**:
- 5 easy-only types (i=9,14,18,61,81): 3 copies each, all in L4+L3 = 15 cells
- 4 bridge types (i=3,7,65,73): 6 copies each, spread L4→L0 = 24 cells
- 9 trap-only types (i=22,24,27,31,43,47,51,56,89): 3 copies each, only L2→L0 = 27 cells
- Total: 15 + 24 + 27 = 66

**Key insight**: Bridge types make revealed tiles feel **familiar**. Player picks type 73 on L4, later sees type 73 again on L2 → "I know this one!" instead of "what is this?".

**CRITICAL RULE**: Bridge types must be **matchable triples** when revealed at bottom — meaning the player can actually see and pick 3 copies to clear. A bridge type that has copies scattered across covered cells is NOT a real bridge. When placing bridge copies at bottom (L1+L0), ensure at least 3 copies become pickable at some point during natural play progression, so the player can form a triple from the bridge type they recognize.

**L3 as transition layer**: Contains both easy-only types AND bridge types — smooth gradient, not a cliff.

**Why this is better than**:
- Pure gradient: no bridge = shock when revealing bottom
- Sharp gradient: cliff at L3 with 11 new types = too harsh
- Cascade: same type vertically looks unnatural + limited to 1-2 stacks

**How to implement**:
1. Calculate: `n_easy × 3 + n_bridge × 6 + n_trap × 3 = total_cells`
2. Assign easy-only to top 2 layers
3. Distribute bridge types across ALL layers (some in top, some in bottom)
4. Assign trap-only to bottom layers
5. L3 (or middle layer) gets mix of easy + bridge = smooth transition
6. v3 solvable + greedy fail check as usual

**Math for L21 (66 cells)**:
- 5 easy(3) + 4 bridge(6) + 9 trap(3) = 15 + 24 + 27 = 66 ✓ (18 types)
- Or: 4 easy(3) + 6 bridge(6) + 6 trap(3) = 12 + 36 + 18 = 66 ✓ (16 types)
