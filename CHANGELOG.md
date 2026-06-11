# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). No tagged releases yet —
everything below is the unreleased line; the first tag will cut it into a version.

## [Unreleased]

### Added
- Nine mining lenses across four source-of-truth families: feature/robustness/issue/
  discussions/config/test/docs-surface (LLM, `lens_mine.py`), operability (deterministic,
  16 probes, `surface_mine.py`), threat (deterministic, OSV-based, `threat_mine.py`).
- Industry-curated gating floor `checklists/generic-software.floor.json` (OpenSSF Scorecard /
  Best Practices Badge / community-profile criteria; the 20-category baseline stays frozen as
  the measurement control).
- The closed loop: `init` → `check` (battery mode, save/from-assessment split) → `emit` task
  queue → Stop-hook + CI gate. `./2080` dispatcher with capability map.
- Controlled measurement: recall-lift instrument (`measure.py`, prepare-once-judge-N fast
  path), gate-recall backtest (`measure_recall.py`), out-of-domain specificity control.

### Changed
- Gating promotion now requires TWO controls (recall lift AND out-of-domain specificity);
  TESTS was promoted on lift (+0.61) and demoted the same day on specificity — the event that
  made the second control mandatory. ISSUES (+0.41) was demoted next by the foreign-domain
  rerun (specificity −0.060 vs zellij). Gating axes: SCOPE only.

### Deprecated
- `archive/cluster_fixes.py` (lost the interleaved control to the robustness-surface lens) and
  `archive/completeness.flow.js` (its target layer is out of scope) — both with documented
  pull-back conditions in `archive/README.md`.

### Security
- `SECURITY.md` added: private vulnerability reporting, trust-boundary map (external repo
  text → prompts; OSV/GitHub responses → deterministic matching only; hostile neighbor clones).
