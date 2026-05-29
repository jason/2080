# 2080

> The last 20% is the hardest — and it's the part agents hide from you.

Agentic development gets you **85% done on day 1, and leaves 85% to go for the
next 3 weeks to 3 months.** The first 85% is the demoable surface. The remainder
is disproportionately the hard 20%: error handling, edge cases, integration
reality, correctness under hostile data, the invisible scaffolding nothing shows.

**2080 makes that hidden work visible and measurable on day 1**, so the second 85%
stops being discovered by crashing into walls one at a time over months.

Start with [`docs/THESIS.md`](docs/THESIS.md). Current state and next step:
[`docs/HANDOFF.md`](docs/HANDOFF.md).

Status: **two working engines, validated in part.** 2080 attacks the second-85% from
two sides: (1) **prior-art transfer** — mine what similar mature repos already had to add
(`find_neighbors.py` → harvest → `cluster_fixes.py` → `checklists/` → `diff_target.py`);
and (2) **adaptive intent-derivation** (`completeness.flow.js`) for the project-specific
residual. The prior-art half is validated (~40% of engineering-debt predicted on a blind
backtest); the adaptive half is built with a self-falsifying answer-key gate, recall not yet
measured. See [`docs/HANDOFF.md`](docs/HANDOFF.md) for the full arc and findings.
