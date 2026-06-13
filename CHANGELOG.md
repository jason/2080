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
- `threat_mine.py --scan <target>`: target-side supply-chain check — direct deps vs OSV,
  findings exit 3 (mirrors the gate); same plumbing as the mining lens.
- Verdict reporting surface: `check.py` JSON now carries `languages` (which languages the
  evidence pass covered) and `summary` (status×tier counts) for CI annotations/dashboards.
- Non-plaintext credentials: `OPENAI_API_KEY_CMD` — an external secret command (OS keychain /
  vault / password manager) whose stdout is the key; never logged, never persisted.
- Assess-path instrument: `measure_recall.py` blocking-precision arm — every gap/partial
  verdict at a historical snapshot adjudicated against the repo's own history (future commits
  built it = right block, past commits already had it = false block). Supersedes the 0.77
  adversarial-refutation precision number; ground truth by construction.
- **Spine registry** ([2080-registry](https://github.com/jason/2080-registry)): published
  spines with provenance, trust tiers (curated/validated/advisory/instrument), and sha256-
  pinned index. `init` stage 0 checks it first — a known app_type downloads verified spines
  in seconds instead of a 30–60 min mine; local files win; any failure falls back to mining.
  Client hardening: hash verification + decoded-string control-char scan on every download.

### Changed
- Gating promotion now requires THREE arms: recall lift, out-of-domain specificity (both
  `measure.py`), and assess-path blocking precision ≥ 0.70 on the candidate's own spine
  (`measure_recall.py`). TESTS was promoted on lift (+0.61) and demoted the same day on
  specificity — the event that made the second arm mandatory. ISSUES (+0.41) was demoted next
  by the foreign-domain rerun (specificity −0.060 vs zellij). The third arm closes the
  "predictive spine, misjudging gate" loophole. Gating axes: SCOPE only.

### Deprecated
- `archive/cluster_fixes.py` (lost the interleaved control to the robustness-surface lens) and
  `archive/completeness.flow.js` (its target layer is out of scope) — both with documented
  pull-back conditions in `archive/README.md`.

### Security
- `SECURITY.md` added: private vulnerability reporting, trust-boundary map (external repo
  text → prompts; OSV/GitHub responses → deterministic matching only; hostile neighbor clones).
