---
name: Hidden trap level design pattern
description: "Trap ẩn" — levels where the obvious greedy path commits the player to a losing trajectory even though the level is solvable
type: feedback
originSessionId: 5bf952b0-04ed-42f3-9813-354182a6e8fb
---
**"Trap ẩn" (hidden trap) levels** are a user-approved design pattern.

**Characteristics**:
- v3 confirms solvable (at least one winning path exists)
- 95-100% of greedy/naive playouts fail (player hits tray full without triple)
- The first few picks LOOK obviously good to a human: several of the same type are visible on top → tempting triple bait
- Taking that bait commits the player to a dead-end trajectory (tray fills later)
- The actual winning path requires picking "wrong-looking" early tiles that don't form immediate triples

**Example (user-approved)**: `trap_an_L20_s82.json`  — L20, 6 layers, 72 cells, 17 types, score 81.91. Player sees easy triples of tile 1 and 3 accessible via tiles 9/3 — but taking them loses. The real winning path starts elsewhere. 300/300 greedy playouts fail, yet v3 finds a solution at depth 72.

**How to find / generate more**:
1. Use `find_l20_17.py`-style script as template (exhaustive knob grid, tight type-count filter, greedy playout filter).
2. Filter: exact tile count + score range + v3 solvable + greedy_fail_rate ≥ 0.90 (300+ playouts).
3. Layouts that trap well: **L20, L6, L30, L50, L115** — deep pyramids with many types make the greedy trap stronger (early triples hide downstream commitment failures).
4. High cc (15-22) with tight distance knob (0-5) concentrates same-type tiles visibly on top, baiting the player.
5. 8 parallel workers via shell fork; first match saves.

**Why:** User said these levels are "rất thú vị" (very interesting) because the trap feels fair — the player can see why they lost (wrong early pick) and is motivated to retry with different strategy or burn a booster.

**How to apply:** When the user asks for a "challenging but solvable" or "need booster to pass" level, default to this metric: v3 solvable + greedy fail rate ≥ 0.90. Don't bother with count_wins absolute count (it hits 10^6+ always and can't discriminate). Random/greedy fail rate is the right lens.
