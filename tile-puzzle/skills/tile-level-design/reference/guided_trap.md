---
name: Guided Trap pattern
description: 3-zone gradient (easy cascade + breadcrumbs + trap cascade) so player doesn't blindly guess hidden tiles — fair challenge, not frustration
type: project
originSessionId: 9cb29a82-5617-4dd8-9f97-2bb165e50048
---
Advanced hybrid pattern that solves the "guessing wall" problem in basic hybrid levels.

**Problem**: Basic hybrid (top=easy, bottom=random trap) → player clears top easily → hits wall of completely unknown trap types → no information → frustrated guessing.

**Solution: 3-zone gradient with breadcrumbs**:
- **Zone 1** (top layer): Easy cascade — instant triples, player clears comfortably
- **Zone 2** (mid layers): Easy types + **breadcrumbs** — 1 copy of each trap type placed on partially-visible cells. Player sees these during Zone 1 clearing → builds mental map
- **Zone 3** (bottom layers): Trap types arranged in **cascade chains** (same type stacked vertically). Player follows chains instead of guessing

**Why:** User observed that random trap in bottom layers forces blind guessing — player has zero information about what's hidden. Breadcrumbs give visual hints during top clearing; trap cascades give structure during bottom clearing.

**How to apply:**
1. Classify cells into 3 zones by layer
2. Zone 1: concentrate 2-3 easy types for instant triples (priority/cascade)
3. Zone 2: fill with remaining easy copies + place 1 breadcrumb per trap type on low-blocker (tier2) cells
4. Zone 3: group trap types into vertical stacks — same type chained top-to-bottom
5. Filter: v3 solvable + fail_rate >= 80% + avg_cleared in target range

**Template**: `find_guided_trap_L21.py`
**Speed**: < 1 second search time (precomputed, optimized)
**Result**: 100% greedy fail, but player experience is "fair challenge" not "blind guessing"
