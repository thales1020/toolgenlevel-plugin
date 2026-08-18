---
name: Verify before play workflow
description: Always double-verify solvability and save exact board data BEFORE opening play window — prevents file overwrite bugs and board mismatch
type: feedback
originSessionId: 9cb29a82-5617-4dd8-9f97-2bb165e50048
---
Always solve and verify the EXACT board data before calling play_level. Never read from a candidate file that 8 parallel workers might overwrite.

**Why:** In a session, 8 workers wrote to the same candidate file. The board loaded into play_level was from an early write, but a later worker overwrote the file with a different (unsolvable) board. The solver then solved the wrong board, producing a solution that didn't match what the user saw on screen.

**FIXED at the root (see `docs/CLAUDE.md` §6):** the `find_*.py` templates used to write to a shared/
hardcoded filename (e.g. `trap_L20_candidate.json`, or worse, a fully hardcoded literal like
`trap_70_90_candidate.json` shared across every layout AND seed) — exactly the collision this doc
describes. Every template now writes `*_s{seed}.json` (unique per worker), and the documented 8-worker
orchestration waits for all workers to finish, then reads back and independently re-verifies each
file before picking a winner, rather than trusting "first success" against a filename other workers
could still be writing to. This closes the race described above rather than just working around it.

**How to apply (still applies — belt and suspenders):**
1. Generate/find candidate → v3 verify → solve_path double-verify
2. Save the verified board to a SEPARATE file (not the candidate file workers write to)
3. Pass that exact saved board dict to play_level
4. For step-by-step solutions, solve the same board dict that was played — never re-read from a shared file
5. When using 8 workers: each worker writes to a UNIQUE file (`*_s{seed}.json`) — this is now the
   required convention, not an either/or option.
