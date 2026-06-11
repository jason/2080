# Contributing to 2080

## Setup

Python 3.11+ and [uv](https://docs.astral.sh/uv/). No install step — tool scripts carry uv
shebangs. LLM-dependent tools need `OPENAI_API_KEY` (any OpenAI-compatible endpoint via
`OPENAI_BASE_URL`); the deterministic tools (`surface`, `threat`, `check --from-assessment`)
need nothing.

```sh
./2080 --json                                   # capability map
uv run --with pytest pytest -q --ignore=archive # full suite (deterministic, no network/LLM)
uvx ruff check --select E9,F63,F7,F82 . --exclude archive
```

## Conventions that are enforced, not aspirational

- **Tests carry intent.** Every test has a one-line `# intent:` comment naming the failure it
  catches. A test that can't fail when the underlying decision changes doesn't ship.
- **Tests are deterministic.** No network, no LLM calls in the suite — stub the HTTP/subprocess
  seams (see `test_threat_mine.py`, `test_lens_mine.py` for the patterns).
- **The gating discipline is tripwire-tested.** A new lens ships ADVISORY (its own axis, not in
  `check.py VALIDATED_GATING_AXES`). An axis earns gating only by passing BOTH measurement
  controls: recall lift over the frozen generic baseline AND out-of-domain specificity above
  the baseline's (`measure.py`; see HANDOFF for the TESTS demotion that made the second
  control mandatory). Do not reuse a validated axis name to make a new lens gate —
  `test_lens_mine.py` will fail.
- **`checklists/generic-software.baseline.json` is frozen.** It is the measurement control
  every historical number was measured against. The gating floor lives in
  `generic-software.floor.json` — edit that one.
- **Agentic CLI surface.** Every command supports `--json`, exit codes are stable and
  documented (0 ok / 1 usage-err / 2 not-found / 3 gated-or-empty), bare `--json` returns a
  capability map.

## Adding a lens

Register an entry in `lens_mine.py LENSES` (source extractor + abstraction prose) or, for
deterministic lenses, follow `surface_mine.py`/`threat_mine.py`. Give it its own axis, add the
registry/tripwire tests, and run it live on real neighbor clones before trusting it — synthetic
tests have missed precision bugs that one live run caught (see HANDOFF session-6).

## Before a PR

1. Full suite green: `uv run --with pytest pytest -q --ignore=archive`
2. Lint clean: `uvx ruff check --select E9,F63,F7,F82 . --exclude archive`
3. If you closed a gap the gate tracks, refresh the committed assessment
   (`docs/INTEGRATIONS.md`, "assessments go stale").
4. Measurement claims need the raw run JSON in `docs/measurements/`.
