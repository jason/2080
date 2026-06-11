# 2080 — Thesis

> **Status addendum (2026-06-10, refreshed 2026-06-11).** This is the founding document, kept
> intact. Measurement has since refined it: the "derive the full requirement surface" bet
> **split by layer**. Robustness derivation is real but a *generic checklist already does it
> better than mining* (lift −0.15 vs a common-sense baseline, replicated) — so the robustness
> floor is now an industry-curated checklist (`generic-software.floor.json`), not a mine.
> **Scope-shaped prediction is the part only mining delivers**: one axis gates — SCOPE (+0.27
> lift; specificity 0.337 vs an adjacent out-domain, +0.474 vs a foreign one). Two others with
> higher lift were both demoted by the specificity controls — TESTS (+0.61, the highest lift
> measured, promoted and demoted the same day) and ISSUES (+0.41, demoted when the
> foreign-domain rerun showed it matched zellij's future work better than its own domain's):
> gating requires beating BOTH controls — lift alone measures breadth. The gap engine exists end-to-end (mine → check →
> emit → stop-hook/CI gate) with measured gate precision 0.77, across nine lenses spanning
> four source-of-truth families (neighbor repos, user demand, industry floors, threat
> landscape). The falsification test below ("does the day-1 map collapse the timeline?")
> remains unrun — it needs a real new project. See `docs/HANDOFF.md` for the full record.

## The problem

Agentic development produces a demo-quality result fast, then the project stalls
for weeks to months. The lived shape:

> **You are 85% done on day 1, and you still have 85% to go.**

The numbers don't add up on purpose — that's the point. The "85% done" is a
*feeling* from a working demo. The remaining work is larger than it looks, takes
far longer than it should, and is where humans get pulled back in.

## Why it happens (root cause)

Two things compound:

1. **Agents are biased toward the demoable.** They optimize for the visible,
   showable surface — the happy path. That front-loads the easy 85% and *defers*
   everything that doesn't demo: error handling, null/concurrent/rollback states,
   integration mismatches, auth/DTO/observability scaffolding, correctness under
   real (hostile) data, the non-functional requirements.

2. **The remaining work is invisible and unmeasurable on day 1.** Because the
   hard parts were deferred, not enumerated, you can't see the iceberg. You
   discover the remaining work *reactively* — by hitting one wall at a time. That
   discovery is serial, and it's the actual reason the tail takes months.

So the residue is not average-difficulty leftover work. It is *disproportionately
the hard 20%*, and it is hidden. The demo manufactures a false completeness
signal; the months are spent re-discovering the spec by failure.

## The product

> **Make the second 85% visible and measurable on day 1, and fight the
> demoable-bias by demanding the invisible work up front.**

Convert *"feels 85% done"* into *"here are the N specific undone things, ranked,
and these M are the hard 20%."* If the iceberg is visible on day 1, the tail
stops being serial-discovery-by-wall-hitting: the work can be planned,
parallelized, and tracked. The slow part was never the *doing* — it was the *not
knowing what was left*.

Concretely, a **completeness / gap engine**:

- **Derive the full requirement surface** from intent — happy path *plus* the
  systematic invisible-20% categories (failure modes, edges, integration
  contracts, non-functional requirements).
- **Measure claimed-done against required**, continuously, and make the **gap**
  the artifact everyone (human + agents) works against.
- **Adversarially hunt what is *not* done.** Treat "done" as a claim to be
  *disproven* until the surface is covered, so the demoable-bias cannot defer
  work into an invisible backlog that surfaces by surprise.

## Tractable now vs. the research bet

- **Research bet (hard):** deriving the *complete* surface including true
  unknown-unknowns. If this were easy it would exist.
- **Tractable now (ship first):** systematically enumerate the *known*
  invisible-20% categories and measure coverage against them. This alone would
  surface most of the iceberg today — without solving unknown-unknowns. The
  solution is not all-or-nothing; there is a shippable ~80% of the answer.

## Non-goals / what this is NOT

- **Not a coordination layer.** Coordinating multiple agents (claims, handoffs,
  collision avoidance — e.g. Agent Rally Point) *prevents waste* while you grind
  the second 85%. It does not *shrink* the 85%. 2080 shrinks it. They are
  different products solving different problems; don't conflate them.
- **Not "more tests."** Tests assert known behaviors. The hard problem is
  enumerating the *required* behaviors — especially the ones nobody specified.
- **Not a demo polisher.** The goal is correctness/completeness of the real
  system, not a nicer happy path.

## The test of the thesis (before building the engine)

The thesis is falsifiable, and we should falsify-or-confirm it cheaply first:

> Take **one real feature**. On day 1, make its second-85% visible (enumerate the
> invisible-20% surface and the gap). Does having that map **collapse the
> timeline** vs. discovering the same work by hitting walls?

If yes, the engine is worth building. If the map doesn't change the outcome, the
thesis is wrong and we learned it for the cost of one feature — not three months.

## Open questions

- What's the smallest artifact that makes the second-85% *visible* for one
  feature? (A ranked gap list? A coverage surface? An adversarial "what's
  missing" pass?)
- How is the requirement surface derived — from the spec, the code, the diff,
  the agent's own plan, or an adversarial model whose only job is to find gaps?
- How do you measure "covered" without it degenerating into test-count theater?
- Where does the human sit — as the arbiter of intent, or out of the loop?
- Does any of Rally's substrate (the fact ledger, managed-session dispatch) help
  *carry/dispatch* the gap, or is 2080 cleanly standalone? (The value is the
  engine either way — don't let sunk cost pull it toward coordination.)
