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

Status: **working pipeline, dogfooded on itself, measured under controls.** The second-85% is
**three layers** — and controlled measurement (2026-06) showed each needs a *different* predictor:

1. **Robustness** — the hidden hard-20% of what you built (error handling, NFRs). **Common sense
   is the better discoverer here**: a hand-written generic checklist out-recalled the mined spine
   (lift −0.15, replicated ×3 — the defect-prediction literature's trivial-baseline lesson, confirmed).
   So every emitted robustness spine ships with the generic baseline as its floor
   (`merge_baseline`), and mining adds sub-type-specific categories + day-1 tells on top.
   The gate enforces only that floor: mined robustness categories are **advisory** by default
   (`check.py` demotes them to `advisory_gaps`; `--enforce-mined-robustness` opts back in).
2. **Generic scope** — features a full product of category X converges on. **This is where mining
   earns its keep**: the feature-surface mine (`lens_mine.py`) beats the generic baseline by
   **+0.27 (±0.05, ×3)** — no common-sense checklist predicts "multi-provider, plugin system, web
   dashboard." *Find* the feature set from mature neighbors, don't imagine it.
3. **Project-specific direction** — the team's actual product bets. *Not predictable, and
   deliberately out of scope* (that's strategy, not completeness).

The gate's verdicts are themselves measured: **blocking-verdict precision 0.77** (adversarial
two-lens refutation on real-sized repos; was 0.083 before evidence-grounded assessment — the fix
was retrieval, not a better model). Gap verdicts must additionally survive a synonym-escalation
second search before they're final. Novelty positioning (verified two-pass survey,
[`docs/PRIOR-ART.md`](docs/PRIOR-ART.md)): the *idea* of neighbor products as scope predictors is
app-store-mining prior art; the commit-mined category spine used as a day-1 predictor **and
enforcement gate** is the unoccupied residue.

Mining is **lens-parameterized**: each axis is a lens. Six ship today — recurring-fix → ROBUSTNESS
(`cluster_fixes.py`); feature-surface → SCOPE, plus issue-surface (GitHub issues = gaps users
actually hit), config-surface, test-surface, and docs-surface (`lens_mine.py` `--lens`); and a
fully deterministic operability-surface lens (`surface_mine.py`, zero LLM calls — Dockerfile/CI/
release/config-example/migrations convergence). **An axis gates only after beating the
generic-baseline control**: SCOPE (+0.27 ±0.05) and ISSUES (+0.41 ±0.06 on scope-layer work, ×3,
disjoint spine pool/targets) have passed; every other axis is advisory — the discipline is
enforced in `check.py` and tripwire-tested. `check.py` is the keystone gate —
`2080 check <target> --spine <checklist>` runs the diff, blocks (exit 3) on applicable required gaps,
and is CI-ready. 2080 was run against its own feature spine and closed 3 of the gaps it found.
See [`docs/HANDOFF.md`](docs/HANDOFF.md) for the full arc and findings.

## Quickstart

Python 3.11+, no packages needed for the core pipeline (measurement extras run via `uv`).
LLM calls go to any OpenAI-compatible endpoint — bring your own key:

```sh
export OPENAI_API_KEY=sk-...           # required (the only setup)
export OPENAI_BASE_URL=...             # optional: OpenRouter / Azure / local server
export LLM_2080_MODEL=gpt-5.5         # optional: override the model every tool uses

./2080 init <your-repo>                # find neighbors → clone → harvest → mine matched spines
./2080 check <your-repo> --spine checklists/<app-type>.*.json --save-assessment .2080-assessments/
# ^ battery mode: ONE merged day-1 map — SCOPE gaps gate, the other axes (operability, issues,
#   config, tests, docs, robustness) render as ranked advisory sections
./2080 check <your-repo> --spine checklists/<app-type>.*.json --from-assessment .2080-assessments/ --json \
  | ./2080 emit --verdict - --format md      # blocking gaps → agent-ready task queue
```

`check` exits 3 while applicable required gaps remain (CI-ready); `--from-assessment` re-gates
deterministically without an LLM. Preflight which backend/model/key source your calls will use
(sources only, never secret values): `python3 check.py --json | jq .llm`. (If a `fan`
parallel-LLM CLI is on your PATH it's used automatically as a local accelerator; nothing
requires it.)

## The loop

2080 is no longer just a report — it's a closed loop from day-1 map to enforced gate:

```
init.py <target|intent>     # acquire matched spines: find neighbors → clone → harvest → mine
check.py <target> --spine S --save-assessment A   # LLM gate run; gaps carry fix_sites (file-level anchors)
emit.py --verdict V         # blocking gaps → agent work queue (acceptance = day-1 tell, verify_cmd per task)
hooks/stop_gate.sh          # Claude Code Stop hook: agent can't claim "done" while the gate is closed
.github/workflows/2080-gate.yml  # CI gate over the committed assessment (no LLM needed in CI)
```

`check.py --from-assessment` re-gates deterministically (no LLM) from a saved assessment, which is
what the hook and CI consume. See [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md).
