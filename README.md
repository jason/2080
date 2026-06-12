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

Mining is **lens-parameterized**: each axis is a lens. Nine ship today — feature-surface →
SCOPE, robustness-surface → ROBUSTNESS (capability-phrased, gating floor merged in),
issue-surface (GitHub issues = gaps users actually hit), discussions-surface (unanswered GitHub
Discussions = demand maintainers never closed), config-surface, test-surface, and
docs-surface (all `lens_mine.py` `--lens`); plus two fully deterministic lenses: the
operability surface (`surface_mine.py`, zero LLM calls — 16 probes: Dockerfile/CI/release/
config-example/migrations/distribution-channels/changelog-discipline/upgrade-guides/telemetry/
CLI-polish convergence) and the threat surface (`threat_mine.py` — neighbor dependency stacks →
OSV advisories → the vulnerability classes this category is empirically exposed to, axis
SECURITY; `2080 threat --scan <your-repo>` runs the same plumbing as a direct supply-chain
check of YOUR dependencies — known-vulnerable deps exit 3, like the gate). The gating floor itself is industry-curated
(`checklists/generic-software.floor.json` — OpenSSF Scorecard/Best-Practices-Badge +
community-profile criteria layered over the frozen 20-category measurement control). **An axis gates only after passing THREE arms** — recall lift over the
generic baseline, out-of-domain specificity above the baseline's (a spine that matches
everything everywhere has breadth, not foresight), and blocking-verdict precision through the
REAL assess path (`measure_recall.py` adjudicates every block against the target repo's own
history at a snapshot). Only SCOPE survives the spine controls (+0.27 ±0.05 lift;
specificity 0.337 vs an adjacent domain, +0.474 vs a foreign one). TESTS scored the highest
lift ever measured (+0.61) and was demoted the same day when the specificity control showed
that lift was breadth (out-of-domain recall 0.86, specificity below the baseline's); ISSUES
(+0.41) followed when a foreign-domain rerun showed it matched a terminal multiplexer's future
work *better* than its own domain's (0.830 vs 0.770). Every other axis is advisory —
the discipline is enforced in `check.py` and tripwire-tested. `check.py` is the keystone gate —
`2080 check <target> --spine <checklist>` runs the diff, blocks (exit 3) on applicable required gaps,
and is CI-ready. 2080 was run against its own feature spine and closed 3 of the gaps it found.
See [`docs/HANDOFF.md`](docs/HANDOFF.md) for the full arc and findings.

## Quickstart

Python 3.11+, no packages needed for the core pipeline (measurement extras run via `uv`).
LLM calls work with **either** an OpenAI-compatible key **or** a Claude subscription —
pick one, nothing else to set up:

```sh
# Option A: any OpenAI-compatible endpoint (bring your own key)
export OPENAI_API_KEY=sk-...           # the only required setup
export OPENAI_BASE_URL=...             # optional: OpenRouter / Azure / local server
export LLM_2080_MODEL=gpt-5.5         # optional: override the model every tool uses

# Option B: Claude subscription — if you have Claude Code installed and logged in,
# there is NO setup: 2080 auto-detects the `claude` CLI and runs calls through it.
# (Force it explicitly with LLM_2080_BACKEND=claude; LLM_2080_MODEL=haiku|sonnet|opus.)

./2080 init <your-repo>                # find neighbors → clone → harvest → mine matched spines
./2080 check <your-repo> --spine checklists/<app-type>.*.json --save-assessment .2080-assessments/
# ^ battery mode: ONE merged day-1 map — SCOPE gaps gate; the other axes
#   (issues, operability, tests, config, docs, robustness, security, discussions) render as ranked advisory
./2080 check <your-repo> --spine checklists/<app-type>.*.json --from-assessment .2080-assessments/ --json \
  | ./2080 emit --verdict - --format md      # blocking gaps → agent-ready task queue
```

`check` exits 3 while applicable required gaps remain (CI-ready); `--from-assessment` re-gates
deterministically without an LLM. Backend auto-detection order: `fan` CLI (local parallel-LLM
accelerator, if installed) → `OPENAI_API_KEY` (native HTTP) → `claude` CLI (subscription).
Override with `LLM_2080_BACKEND=native|fan|claude`. Preflight which backend/model/key source
your calls will use (sources only, never secret values): `python3 check.py --json | jq .llm`.

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
