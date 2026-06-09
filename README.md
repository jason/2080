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

Status: **working pipeline, dogfooded on itself.** A blind backtest (dexto) showed the
second-85% is **three layers**, each with its own predictor:

1. **Robustness** — the hidden hard-20% of what you built (error handling, NFRs). Predicted by
   intent-derivation (`completeness.flow.js`) + the recurring-fix mine (`cluster_fixes.py`).
2. **Generic scope** — features a full product of category X converges on. Predicted by the
   **feature-surface mine** (`feature_mine.py`) — *find* the feature set from mature neighbors,
   don't imagine it.
3. **Project-specific direction** — the team's actual product bets. *Not predictable, and
   deliberately out of scope* (that's strategy, not completeness).

Mining is **lens-parameterized** (`mine_common.py`): each axis is a lens (recurring-fix → robustness,
feature-surface → scope; future: integration/threat/operability). `check.py` is the keystone gate —
`2080 check <target> --spine <checklist>` runs the diff, blocks (exit 3) on applicable required gaps,
and is CI-ready. 2080 was run against its own feature spine and closed 3 of the gaps it found.
See [`docs/HANDOFF.md`](docs/HANDOFF.md) for the full arc and findings.

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
