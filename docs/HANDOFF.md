# 2080 — Handoff

_Last updated: 2026-05-28_

## Where this came from

Spun out of an Agent Rally Point (`~/projects/agent-rally-point`) session. That
work built a coordination layer (predictive contract claims, handoff receipts, a
CI gate). The conclusion that created 2080: **coordination is a cost-reducer, not
a quality-improver** — it prevents agents colliding but does nothing about the
real bottleneck of agentic development, which is the second-85% / last-20%
completion problem. That problem is a *different product*. This is it.

## Current state

- **Thesis captured** (`docs/THESIS.md`). No code yet — deliberately.
- This is the stage where the rule is: **prove the thesis before building the
  engine.** Don't build a gap-engine on faith.

## Next step (the one that matters)

Run the thesis test on **one real feature**:

1. Pick a concrete feature in a real repo.
2. On day 1, produce its "second-85% map" by hand or with a throwaway script:
   enumerate the invisible-20% surface (failure modes, edges, integration
   contracts, non-functional reqs) and the gap vs. what's built.
3. Build the feature *with* the map visible, and observe: does the map collapse
   the timeline vs. discovering the same work by hitting walls?

If yes → design the engine. If no → the thesis is wrong; we learned it for one
feature, not three months.

## Decisions on record

- **Name:** `2080` — "the last 20% is the hardest."
- **Separate from Rally.** Rally may later be useful substrate (fact ledger,
  session dispatch) but is not the value; 2080's value is the gap engine.
- **Ship-first scope:** the *known* invisible-20% categories + coverage, not the
  unknown-unknowns research problem.
