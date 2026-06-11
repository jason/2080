# 2080 — Handoff

_Last updated: 2026-06-11 (foreign-domain rerun: ISSUES demoted; DISCUSSIONS provisional pass; floor calibrated)_

## 🔬 Foreign-domain rerun: ISSUES demoted — SCOPE is the only gating axis

The follow-up flagged in the specificity-control entry below ran 2026-06-11. Same instrument
(measure.py unchanged, pre-registered rules frozen in the analyzer BEFORE results), out-domain
now fully foreign: terminal multiplexers (tmux, zellij) — no LLM-app vocabulary overlap. Raw
JSON + analyzer + leak-free discussions spine: `docs/measurements/issues-discussions-control.json`,
`analyze_idc.py`, `telegram.discussions3.json`.

**Instrument finding first:** tmux and karfly (chatgpt_telegram_bot) produced EMPTY scope-layer
answer keys — tmux's recent 130 items classify as 95 robustness + 35 churn, zero scope (a
26-year-old finished tool adds no new generic capabilities; the layer classifier is working,
not broken). They drop from scope-layer comparisons legitimately. Effective groups:
in=dexto/goose/cline, out=zellij (key n=23), tg=nekro (n=38) + n3dbot (n=3).

| spine (scope layer) | in(cli) | out(zellij) | specificity |
|---|---|---|---|
| issue-surface (ISSUES) | 0.770 | **0.830** | **−0.060 → DEMOTED** |
| feature-surface (SCOPE) | 0.514 | 0.040 | **+0.474 — survives its 2nd specificity pass** |
| generic baseline | 0.336 | 0.417 | −0.081 (the bar) |

- **ISSUES demoted** by the pre-registered rule (demote if ≤ baseline+0.05). It matched a
  terminal multiplexer's future work BETTER than its own domain's — the adjacent-domain 0.112
  wasn't partial transfer, it was breadth. Same failure as TESTS, now with the loophole
  ("adjacent domain is inconclusive") closed. `VALIDATED_GATING_AXES = {"SCOPE"}`; tripwire,
  capability maps, README, THESIS, CHANGELOG all updated.
- **SCOPE re-affirmed** on a second, harsher out-domain: +0.474 specificity (vs +0.337
  adjacent). It is now the only axis that has passed lift + two different specificity passes.
- **DISCUSSIONS control (provisional PASS, NOT promoted):** 3-neighbor leak-free spine
  (AstrBot/LangBot/ChatGPT-Telegram-Bot mined; nekro-agent held out), judged on telegram
  targets. Lift +0.452 mean, all 3 runs positive (bar ≥+0.15); specificity in(tg)−out(cli+mux)
  = +0.248 vs baseline −0.151 (bar passed). BUT: only 2 usable in-domain targets and n3dbot's
  answer key has 3 items — the pass rests mostly on nekro. Promotion bar: ≥3 in-domain targets
  with ≥10-item keys. Until then DISCUSSIONS stays advisory.
- **Floor calibration shipped (same session):** clause (c) added to diff_target's na rules —
  generic floor categories must be REINTERPRETED in sub-type terms (CLI "UI/UX polish" =
  help-text/error-message/output quality; i18n = Unicode handling; telemetry for a
  privacy-deliberate local tool = logs or na). Re-gated 2080 on its own floor: 22 → 17
  blocking, and the remaining partials now reason in CLI terms (verified by reading verdicts;
  saved run: /tmp/floor-recal.json pattern, rerun any time). Partials stay blocking:
  **Picked:** keep `--fail-on partial` default and fix verdict accuracy, **Over:** demoting
  floor partials to advisory, **Why:** the strict day-1 map is the product and `--fail-on gap`
  already exists for looser teams. **Rejected fate:** documented here, nothing to remove.

## 🔬 Out-of-domain specificity control: TESTS demoted; gating now requires TWO controls

The breadth caveat on TESTS was tested the same day it was recorded. Instrument: same
measure.py protocol, but the gating spines were ALSO judged against three out-of-domain
targets (AstrBot/LangBot/ChatGPT-Telegram-Bot answer keys — telegram bots, disjoint from the
cli spine pool). A spine with real domain foresight should recall in-domain work far better
than out-of-domain work; a breadth artifact matches everything everywhere. Specificity =
in-recall − out-recall, compared to the generic baseline's (×3 repeats, 2 judges, one batch;
raw JSON + analyzer: `docs/measurements/specificity-control{.json,/analyze_specificity.py}`).

| spine (scope layer) | in-recall | out-recall | specificity |
|---|---|---|---|
| feature-surface (SCOPE) | 0.562 | 0.226 | **0.337 — real foresight (3× baseline)** |
| issue-surface (ISSUES) | 0.799 | 0.687 | 0.112 — baseline-level (see caveat) |
| test-surface (TESTS) | 0.939 | 0.861 | **0.078 — BELOW baseline → demoted** |
| generic baseline | 0.309 | 0.200 | 0.109 (the bar) |

(Robustness layer confirms: TESTS specificity 0.159 vs baseline 0.176.)

- **TESTS demoted** (`VALIDATED_GATING_AXES = {SCOPE, ISSUES}` again; tripwire updated). Its
  +0.61 lift — the highest ever measured here — was breadth: behavior-area labels match ~any
  software project's future work (0.86 recall on telegram bots it never saw). **Codified
  lesson: lift over the baseline is necessary but NOT sufficient; a gating axis must also be
  more domain-specific than the baseline.** Both controls now documented as the promotion bar.
- **ISSUES caveat, deliberately NOT demoted:** its specificity (0.112) sits at baseline level,
  but the out-domain is ADJACENT — telegram LLM bots genuinely share issue vocabulary with
  agent CLIs (provider errors, API keys, model config), so shared-content recall is partly
  real transfer, not pure breadth. Inconclusive by this instrument. Follow-up flagged: rerun
  with a fully-foreign out-domain (e.g. terminal multiplexers) before re-affirming or demoting.
- Instrument note: this control reuses measure.py unchanged (extra `--target` args + variants);
  no new code shipped — the analyzer is 30 lines in docs/measurements/.

## 🧪 Five-lens control battery (2026-06-11, fast path: 5m17s for 5 lenses × both layers × 3 repeats)

One measure.py run (5 variants in both layer slots, frozen baseline control, ×3 repeats, one
~900-call judge batch — which exposed and fixed a flat fan subprocess-timeout ceiling; it now
scales with wave count, tripwire-tested):

| lens | robustness-layer lift | scope-layer lift | verdict |
|---|---|---|---|
| **test-surface** | **+0.28 ±0.00** | **+0.61 ±0.01** | **PROMOTED** — then DEMOTED same day by the specificity control (see top entry): the lift was breadth |
| docs-surface | −0.27 ±0.03 | +0.43 ±0.07 | advisory — scope pass but material robustness loss (ISSUES precedent was parity, not loss) |
| config-surface | −0.38 ±0.00 | +0.10 ±0.02 | advisory — marginal, and the cli-pool spine mined dev-tooling config, not product knobs; re-test after lens improvement |
| operability | −0.54 ±0.02 | −0.33 ±0.02 | advisory — instrument mismatch: feat/fix-commit answer keys undersample artifact work |
| threat (SECURITY) | −0.63 ±0.01 | −0.33 ±0.02 | advisory — same instrument caveat, vuln classes ~never commit subjects |

`VALIDATED_GATING_AXES = {SCOPE, ISSUES, TESTS}`. Honest caveat on TESTS recorded here: its
absolute recall is very high (0.94–0.95) and test categories partially mirror the whole work
surface (behavior-area labels), so some of its lift may be breadth rather than foresight — the
control corrects judge leniency, not spine breadth. It passed the same bar as every promotion;
flagging for a breadth-normalized follow-up instrument if it ever gates noisily in practice.
DISCUSSIONS control was attempted and is UNRUNNABLE on the cli pool: only gptme has GitHub
Discussions enabled — needs a pool with ≥2 Discussions-enabled neighbors. Battery JSON:
docs/measurements/lens-controls-battery.json.

## ⏩ Session-6: industry floor + three new source-of-truth families (109 tests green)

Research finding that framed the work: all prior lenses mine ONE source of truth (neighbor git
repos = the supply side). Built the first lenses over three missing families — curated industry
floors, demand-side voices, and the threat landscape. Prior art absorbed, not reinvented:
OpenSSF Scorecard already productizes deterministic repo-floor scoring; LLM-Cure
(arXiv 2409.15724) is peer-reviewed neighbor-review mining (73% of proposals later shipped).

- **Industry-curated gating floor** (`checklists/generic-software.floor.json`): 25 required +
  5 optional, every entry with a verifiable day1_tell. Superset of the 20-category baseline —
  new categories distilled from OpenSSF Scorecard / Best Practices Badge / GitHub community
  profile (security policy, license clarity, contribution docs, changelog discipline, static
  analysis; release integrity / SBOM / fuzzing / deprecation policy / privacy as optional).
  `lens_mine --baseline` default now points here and `merge_baseline` carries day1_tell/tier
  through. **`generic-software.baseline.json` is FROZEN as the measurement control** — every
  historical lift number was measured against it; the floor/control role split is deliberate.
- **SECURITY axis exists now** (`threat_mine.py`, `./2080 threat`, deterministic, no LLM):
  neighbor manifests (npm/PyPI/crates.io/Go) → OSV querybatch → ordered keyword classification
  → per-vulnerability-class spine (required at ≥2 affected neighbors). Live smoke: 2-dep repo →
  21 vulns → deserialization + secrets-exposure categories with real PYSEC examples. Advisory
  until it beats the control (tripwire-tested like every unvalidated axis).
- **discussions-surface lens** (`lens_mine.py`, axis DISCUSSIONS, advisory): the demand-side
  sibling of the gate-earning ISSUES lens — unanswered GitHub Discussions ranked by
  upvotes+comments, gh GraphQL, cached, degrades gracefully when a neighbor has Discussions
  off. Candidate for the next measure.py control run (ISSUES protocol, same pools).
- **operability lens: 11 → 16 probes** (`surface_mine.py`, probe shape generalized to optional
  content regexes): distribution channels (brew/deb/winget/snap/PKGBUILD/goreleaser),
  changelog discipline (Keep-a-Changelog structure, presence ≠ contract), migration/upgrade
  guides + deprecation lifecycle, telemetry instrumentation, CLI polish (completions/man).
- Deliberately descoped: G2/Capterra category feature lists (DataDome WAF + ToS; and the
  dev-tool control pools can't validate them). Next demand-side tier if wanted: SO-tag mining
  (LiFUSO), HN Show-HN critique, app-store review mining (LLM-Cure protocol).
- **All four golden paths live-verified on real corpora (not just the 110-test suite):**
  - `threat` on the 4 telegram neighbors: 308 deps → 662 OSV vulns → 9 convergent required
    classes (ReDoS/DoS/secrets-exposure/memory-safety at 4/4) with real PYSEC examples.
  - `surface` on the same corpus **found 4 precision bugs the synthetic tests missed** — CLI
    polish matched `changelogs/v3.4.1.md` as a man page; `### Added` in random docs scored
    changelog discipline; `@deprecated` in source claimed upgrade guides; opentelemetry in
    `uv.lock` claimed instrumentation; `generate_completion` in a bundled shiki runtime is LLM
    vocabulary, not shell completions. Fixed via content-hit hygiene (`filter_content_hit`:
    lockfile + vendored-bundle exclusions, per-probe path filters) + regex tightening; the
    post-fix live run cites only real evidence (`docs/MIGRATION_SUMMARY.md`, honest zeros).
  - `mine --lens discussions-surface` end-to-end (gh GraphQL + fan synthesis): 3 convergent +
    7 optional, face-valid demand ("Model/API compatibility diagnostics", "plugin lifecycle").
  - **Floor dogfood:** `check . --spine generic-software.floor.json` → 22/25 blocking on 2080
    itself. Verdicts are evidence-grounded and largely TRUE (no release artifacts, no security
    policy, no changelog…) — the floor IS the second-85% map for this repo. Calibration flag:
    i18n and UI/UX polish blocked on a developer CLI — na_by_design / sub-type interpretation
    may need a floor-aware pass before the floor blocks CI anywhere.
- Next steps: run the DISCUSSIONS control (measure.py, ISSUES protocol); decide floor gate
  calibration (strict day1_tells make partials block — feature or bug?); re-run a battery on a
  real external target with floor+threat included; consider OSV-scanning the TARGET's own
  lockfile in check.py (target-side, not neighbor-side — different tool shape).

## ⏩ Session-5c: ISSUES lens EARNS the gate (+0.41 ×3); battery day-1 map; consolidation

- **The issue lens passed the control and was promoted.** Protocol identical to the SCOPE
  validation: issue-surface spine mined from aider/gptme/openinterpreter (pool DISJOINT from
  targets dexto/goose/cline), measure.py strict 2-judge recall lift vs the generic baseline, ×3
  back-to-back runs. **Scope-layer lift +0.41 ±0.06** (run lifts +0.35/+0.47/+0.42; every
  target positive every run); robustness-layer +0.02 ±0.03 (baseline-parity — the layer-split
  confirmed a third independent way). `VALIDATED_GATING_AXES = {SCOPE, ISSUES}`; the
  test_lens_mine tripwire now keys gating to an explicit CONTROL_PASSED set with the numbers.
- **Battery mode shipped** (`check.py --spine a.json b.json …`): one merged day-1 map — gating
  axes block, other axes render as ranked advisory sections; per-spine assessments in a
  directory; `blocking_gaps` stays flat so emit consumes batteries unchanged. `./2080`
  dispatcher + pyproject; init.py now also mines the free operability spine every run.
- **VIP vs issues+operability battery (advisory richness check): PASS with 15 advisory items**
  that read like a real backlog — tool/plugin governance, multimodal handling, schema/data
  migrations (vecstore!), release automation, packaging. Map at /tmp/vip-advisory-map.txt.
- **Consolidation:** feature_mine.py → lens_mine.py (mines six surfaces); new
  robustness-surface lens (capability-phrased, the cluster_fixes successor candidate).
- **Supersession SETTLED (2026-06-11, interleaved ×3 control, same targets/conditions):**
  robustness-surface lift **−0.04 ±0.02** (recall 0.59–0.64) vs cluster_fixes **−0.20 ±0.04**
  (recall 0.46–0.51) — capability phrasing closes most of the gap to the generic baseline with
  no embedding stack. cluster_fixes + its tests → `archive/` (README has the pull-back
  criteria); `merge_baseline` (the gating floor) moved to lens_mine and applies to every
  ROBUSTNESS-axis emission; `embed`/`abstract_via_fan` moved into measure.py (last consumer);
  init.py mines robustness via the lens now. ROBUSTNESS stays advisory (still doesn't beat the
  baseline) — but its advisory content is now judgeable capabilities, not change-labels.
  Also fixed live: lens attribution (normalized name matching + neighbors REQUIRED in the
  synthesis prompt) — identity-poor material had zeroed the required tier.

### ⚡ measure.py prepare-once-judge-N (2026-06-11) — 13× faster controls, same statistics
One process now takes N spine variants per layer (`--robustness-spine a.json b.json`), `--repeats
N`, and puts ALL judge calls (variants × repeats × null) in ONE fan batch; answer keys, layer
classification (now content-hash cached, layers.json), abstraction, and embeddings compute once.
Verified: the 2-variant ×3-repeat control that took ~40 min serial ran in **3m04s**, reproducing
the unchanged-input variant within noise (cluster_fixes −0.213 ±0.018 vs serial −0.200 ±0.036).
Repeats stay independent judge samples; variants within a repeat share the same null sample —
interleaving by construction. Side-finding: the floor-merged robustness-surface spine lifts
+0.12 ±0.09 over the bare baseline (floor + mined detail > baseline alone; high variance, n=3).

## ⏩ Session-5b: five new mining lenses (published repo: github.com/jason/2080, public)

The lens registry earned its keep — four new LLM lenses are LENSES entries in `lens_mine.py`
(source + abstract prose, shared synthesis): **issue-surface** (ISSUES axis — GitHub issues =
gaps users EXPERIENCED, reaction-weighted, PRs excluded, gh-cached), **config-surface** (CONFIG —
config files + recurring env keys → knob groups), **test-surface** (TESTS — test files/names →
verification spine), **docs-surface** (DOCS — md headings → support surface). Plus
**surface_mine.py**: a fully deterministic operability-surface lens (OPERABILITY — Dockerfile/
compose/CI/release/config-example/migrations/healthcheck/packaging probes; zero LLM calls).

**Gating discipline generalized and codified:** `check.py` now has `VALIDATED_GATING_AXES =
{"SCOPE"}` — mined categories on ANY other axis (ROBUSTNESS and all five new ones) are advisory;
the generic-baseline floor and axis-less user checklists still gate; `--enforce-mined` (alias
`--enforce-mined-robustness`) opts back in. Tripwire tests enforce it from both sides
(test_lens_mine: no lens may ship axis SCOPE without the control; test_surface_mine +
test_check_assessment: new axes demote). A lens earns gating by beating the generic-baseline
control in measure.py — same bar SCOPE passed (+0.27).

All six lenses live-ran on the telegram neighbors → `checklists/telegram-llm-bot.{issues,configs,
tests,docs,operability}.json` (10/7/13/20/10 required). Operability is 3-4/4 convergent on
containerization/compose/CI/release/config-example — exactly the demo-invisible material the
thesis names. Next: assess VIP against the issue + operability spines (advisory richness), and
run a measure.py control on the issue lens (the one most likely to earn gating).

## ⏩ Session-5 update: gate matches the measurement, recall measured, open-source cut

Three moves, all verified (54 deterministic tests green):

- **Robustness gate now matches the layer-split verdict (codified).** Spines carry an `axis`
  (`ROBUSTNESS` from cluster_fixes, `SCOPE` from lens_mine; existing checklists backfilled).
  `check.py` demotes mined ROBUSTNESS-axis required gaps to `advisory_gaps` — only the
  `origin: generic-baseline` floor gates; `--enforce-mined-robustness` opts back in. Re-gating the
  saved VIP robustness assessment: **97 blocking → 2 blocking** (release versioning, caching —
  both floor) **+ 95 advisory**. The change-shaped-labels finding is now enforced by the gate
  itself, not a HANDOFF paragraph.
- **Gate RECALL measured for the first time** (`measure_recall.py` — precision 0.77 was only half
  of gate quality). Protocol: snapshot a neighbor at 25% of its FULL history, ground-truth = spine
  categories its future commits introduced (2 strict introduction-judges, full agreement, ≥2
  commits), run the real assessor on the snapshot. **LangBot @ 2023-05-21 (896/3581 commits):
  mean recall 0.54 (runs 0.62/0.46, n=2) over 13 ground-truth categories.** Two miss families,
  both instructive: (a) `na_by_design` misses — admin dashboard + dashboard auth na'd at the
  snapshot's inferred sub-type, but the project later GREW into them: na_by_design is a bet on
  intent, and intent grows (stable across both runs); (b) `covered` misses on categories present
  in embryo that the future "built out" (residual ground-truth ambiguity). v0.1 lesson recorded
  in the tool: snapshotting inside the recent-500 harvest window = mature-product snapshot =
  contaminated ground truth (measured 0.25 "recall" that was really correct-covered verdicts).
  Follow-ups: leave-one-out spine, more repos/runs, majority-of-3.
- **Open-source cut.** `mine_common` grew a stdlib-only native OpenAI-compatible backend
  (OPENAI_API_KEY + OPENAI_BASE_URL, threaded, same retry net) behind the one `fan_batch` seam;
  `fan` demoted to optional accelerator (auto-used iff on PATH; `LLM_2080_BACKEND` pins).
  `LLM_2080_MODEL`/`LLM_2080_PROVIDER` override every tool at once. MIT LICENSE, README
  quickstart (BYOK-first), machine-local paths scrubbed from docs, git author identity rewritten
  across all history. Self-gate: **4 blocking → 1 → PASS expected** after the BYOK
  request-path test (test_mine_common.py proves configured key/base URL land in the actual HTTP
  request) and a BYOK preflight surface (`check.py --json | jq .llm` — backend/model/key SOURCE,
  never values). **Self-gate: 4 blocking → 1 → PASS (0/14 blocking), offline re-gate confirms.**
  Repo creation + push needs the user (harness blocks new-remote pushes):
  `gh repo create 2080 --private --source . --push`, then flip public when ready.

## ⏩ Session-3 update: the loop closed (visibility → enforcement → work queue)

Four lanes built in parallel (workflow, worktree-isolated) and merged; all 37 deterministic
tests green on the merged tree:

- **`emit.py`** — gap → agent work queue. Consumes a `check.py --json` verdict (file/stdin) or runs
  live; each blocking gap becomes a task spec: stable slug id, `acceptance` = the day1_tell verbatim,
  evidence (passes through `fix_sites`), and a `verify_cmd`. `--format md` renders an
  acceptance-checklist backlog. This is the day-1 work queue an implementing agent consumes.
- **`init.py`** — one-command matched-spine acquisition: intent (or target README) → `find_neighbors`
  → idempotent blob-less clones (`~/.cache/2080/`) → harvest JSONs → `cluster_fixes` (robustness
  spine) + `lens_mine` (scope spine) → `checklists/`. Consent before spend (`--yes`), `--dry-run`,
  `--neighbors` override, `--max-commits` cost cap. **Full live mine not yet run end-to-end** —
  stage seams individually tested.
- **Gate integrations** — `check.py --save-assessment/--from-assessment` splits the LLM assessment
  from the deterministic gate (offline re-gate verified byte-identical to live). On top:
  `hooks/stop_gate.sh` (Claude Code Stop hook; exit 2 + gap report when gated, **fails open** on all
  error paths) and `.github/workflows/2080-gate.yml` (CI over the committed `.2080-assessment.json`;
  dormant, no remote). `docs/INTEGRATIONS.md` documents both. `.2080.json` now live in this repo.
- **`diff_target.py` evidence** — every gap/partial now carries `fix_sites` (1-3 `{file, what}`
  anchors from the real fileset, deterministically validated like cited_files; hallucinated paths
  dropped + flagged `fix_sites_unverified`). Verified live: 2080's own gaps got real anchors.

**Dogfood state:** live gate on 2080 itself = 5 blocking of 14 required (was 6). The remaining gaps
(provider-selection, BYOK, PR-integration, enterprise-secrets, reporting) are now emitted as a task
queue with fix sites — close them with `emit.py --target . --spine checklists/ai-codebase-gap-analysis.features.json --format md`.

### ⚖️ Generic-baseline control + variance (session 4) — THE THESIS SPLITS BY LAYER

The MATTER-style control ran (3 repeats vs `checklists/generic-software.baseline.json`, a
20-category no-mining common-sense checklist; plus 2 repeats vs the tmux/zellij null for
continuity; strict 2-judge, dexto/goose/cline, fresh full clones):

| control | robustness lift | scope lift |
|---|---|---|
| tmux/zellij (wrong domain) | **+0.44** (sd 0.01) — reproduces the headline | **+0.51** (sd 0.06) |
| **generic checklist (common sense)** | **−0.15** (sd 0.01, replicated ×3) | **+0.27** (sd 0.05) |

- **The robustness mining FAILS the trivial-baseline control.** A hand-written generic checklist
  recalls later robustness work BETTER than the mined sub-type spine (0.63 vs 0.48). The CPDP
  literature's warning came true for this layer: robustness work is largely universal. (Nuance:
  the weak ML signal disagrees on sign, +0.10 mined — granularity confound: 20 broad categories
  match more easily than ~100 narrow ones. But by the primary instrument, generic wins.)
- **The scope mining SURVIVES it** (+0.27±0.05, replicated). Generic checklists cannot predict
  "multi-provider / plugin marketplace / web dashboard"; mining can. **Scope prediction is 2080's
  measured differentiator.**
- **Product implication:** the robustness layer should ship AS a generic baseline (free, no
  mining) with mined sub-type categories as additive day-1 tells/gating detail — not as the
  discovery mechanism. The mining pipeline's pitch narrows to the scope layer + the gate loop.
- **Assessment stability (3 repeated goose runs, escalation active):** 16/28 required categories
  identical across all 3 runs (57%); all flips are adjacent (covered↔partial↔gap, never
  covered↔gap... except via gap-lift); aggregate blocking count is steady (22/22/24); gap counts
  0/4/3. For gate use, a majority-of-3 assessment mode (~3× cost, cents) would stabilize
  per-category verdicts — not built, noted as an option.

### 🐕 VIP-bot dogfood (session 4) — first real external target; relevance fixed live

Ran a local personal Telegram-LLM-bot repo ("VIP", 351 files, TS/bun) against both telegram
spines. First pass exposed the next
quality frontier: verdicts factually right but **strategically irrelevant** — a personal
single-user bot gated on admin dashboards, plugin marketplaces, onboarding flows, i18n
(framework-product features from the AstrBot/LangBot neighbor set). Plus the 194-cat robustness
spine blew the single-call ceiling entirely.

Both fixed and live-verified (`diff_target` v0.4):
- **Sub-type-aware assessment:** `infer_sub_type` runs first; every verdict judged against what
  THE TARGET's sub-type requires, with multi-user-product-vs-personal-tool examples in the
  na_by_design rules. VIP scope blocking: **13/17 → 4/17**, all 9 flips being exactly the
  framework-product features, each with sound reasoning.
- **Chunked assessment** (ASSESS_CHUNK=40, parallel fan chunks, per-chunk failure containment):
  the robustness spine now completes (5 chunks).

VIP's actual day-1 map (scope): 4 partials — provider/model management, agent command system,
knowledge-base/document QA, rich message handling. Queue at /tmp/vip-scope-queue.md.

**New finding from the robustness run: mined robustness categories are change-shaped, not
capability-shaped.** 97/117 required blocking on VIP — labels like "dependency fix", "type usage
fix", "module import fix" are cluster names of FIXES, not requirements a target can satisfy, so
the gate drowns in mushy partials. Confirms (again, from a new angle) the layer-split verdict:
gate on the SCOPE spine + the generic-baseline robustness floor; treat the mined robustness
detail as advisory tells, not blocking categories. **Codified (2026-06-10):** spines carry an
`axis` (`ROBUSTNESS` from cluster_fixes, `SCOPE` from lens_mine); `check.py` demotes mined
ROBUSTNESS-axis categories to `advisory_gaps` by default — only `origin: generic-baseline` floor
categories gate; `--enforce-mined-robustness` restores full gating. Re-gating the VIP robustness
assessment: 97 blocking → 2 blocking (release versioning, caching — both floor) + 95 advisory.
The alternative codification (capability-phrased abstraction prompt in cluster_fixes) remains
open as a way to EARN mined robustness back into the gate.
(Nuance noted: 'sandbox runtime' / 'tool permissions' na'd as product features is correct
scope-wise; the bot's real sandboxing/security concerns are robustness-side and already active
work in that repo — tainted-mode commits.)

### Precision measurement (session 3, later): THE GATE IS BLIND ON LARGE REPOS

Adversarial refutation (2 independent lenses per verdict, FP only when both refute with ≥med
confidence) over diff_target verdicts:

- **Blocking-verdict precision on goose: 0.083** — 22 of 24 required gap/partial verdicts were
  false positives, most refuted with HIGH confidence by both lenses (goose has a typed error
  taxonomy, clap error reporting, layered config, 30+ providers... all called "gap").
- **Root cause (visible in refuter evidence): evidence starvation in `gather_evidence()`** —
  first 80 files from `git ls-files` (alphabetical → `.github/` first) + 13KB source excerpt.
  On a 10-crate Rust workspace the assessor literally judged a CI helper script as "the app"
  (one verdict's reasoning says "the script..."). Small repos are fine: 2080's own sampled
  covered verdicts stood 4/4; goose's "Model/provider support: covered" stood. cline's
  "command error reporting: covered" had fabricated reasoning (1 of 6 covered samples false).
- **Implication:** recall-lift numbers (measure.py, which judges answer-key items against spine
  categories, no diff_target involved) are NOT invalidated. But `check.py`/`diff_target` verdicts
  on any real-sized repo are currently untrustworthy — **fix evidence gathering before the live
  thesis test**. Direction: category-aware retrieval (grep keywords from category/day1_tell
  across the full tree, feed matched snippets) and/or a two-pass file-selection step; drop the
  alphabetical-80 cap. 41 of 65 gap/partial verdicts went unchecked (cap) — re-run after the fix.

**FIXED + RE-MEASURED (same session): precision 0.083 → 0.767.** `gather_evidence` rebuilt:
per-category parallel `git grep` over the full repo (3.8s on goose, was 136s serial), evidence
candidates filtered to source/docs/config (lockfiles/minified/vendored blobs were outranking real
source), full fileset for citation validation, dir-map instead of the alphabetical file dump.
Controlled re-run, same refutation protocol, cap 30: **precision 0.767** (30 verdicts: 24 goose /
6 cline; 7 FP). Breakdown: **partial verdicts 22/26 stand (0.85)**; **gap verdicts only 1/4 stand**
— the residual weakness is `gap` calls where the capability exists under vocabulary the category
keywords miss (e.g. optional-dependency handling implemented as `ensure_peekaboo()`).

**Synonym escalation BUILT (session 4):** before any `gap` verdict is final, the LLM proposes
implementation-vocabulary terms, the same deterministic grep re-runs, and a re-judge can lift the
gap (flip keeps an audit trail: `escalated` + `pre_escalation_reasoning`; survivors are flagged
`gap-survived-synonym-search`). Live goose run: 'path completion filtering' flipped to partial
(found rustyline FilenameCompleter); 'optional dependency handling' still survived — the synonym
list didn't guess `peekaboo`, so escalation reduces but does not eliminate vocabulary mismatch
when the implementation name is genuinely unguessable. Verdicts also vary run-to-run (LLM
sampling): same goose assessment produced 5 then 3 then 2 gaps across runs — a variance bound
on the precision number needs repeated runs if rigor is wanted. Covered sample: 5/6 stand (1 false-covered: platform compatibility credited
from a build-only Windows CI job). Unchecked due to cap: 16 gap/partial, 17 covered.

### init.py live-verified end-to-end (session 3, later still)

First full live run (intent: telegram-LLM-bot): discovery → 4 high-maturity neighbors
(AstrBot 4778c, LangBot 3581c, ChatGPT-Telegram-Bot 1163c, nekro-agent 879c) → clones →
harvests (500c each) → both mines. Output: `checklists/telegram-llm-bot.{robustness,features}.json`
(97 required robustness categories @ 68.3% recurrence; 17 convergent scope capabilities) — the
spine-library seed, pointable at the VIP bot for a real-project dogfood.

Two findings from the run:
- **Bug found + fixed:** find_neighbors classified the intent as `ai-agent-tool`, silently
  overwriting the aider/OI/gptme scope spine of that name. Restored from git; outputs renamed
  to `telegram-llm-bot.*`. init.py now refuses to overwrite existing spines without `--force`
  (exit 1, suggests `--app-type`; test added, 13/13 green).
- **Quality caveat:** the robustness spine's top cluster is a 334-commit catch-all
  ("empty response handling / dependency fix / identifier parsing fix") spanning all 4 neighbors —
  the known catch-all inflation shape. Re-tune eps or split that cluster before trusting the
  97-category count; the scope spine looks clean.
  **FIXED (session 4):** eps sweep on the telegram corpus showed the knee is corpus-dependent —
  at the default 0.34: maxClust 334, silhouette 0.084; at **0.26**: maxClust 25, silhouette 0.525,
  recurring clusters 97→115. Re-emitted at eps 0.26: top clusters are now coherent (25-commit
  error-handling, 17-commit timeout-handling). **Lesson CODIFIED:** `--eps auto` is now
  cluster_fixes' default — sweeps the grid and picks per-corpus via `pick_eps` (catch-all guard:
  maxClust ≤5% of clustered; silhouette ≥0.3; maximize recurring clusters). Tested against the
  real telegram sweep numbers; live auto run reproduces the 0.26 choice unattended.

**Prior-art survey: VERIFIED** (103 agents, 22 confirmed / 3 killed claims) → `docs/PRIOR-ART.md`.
Verdict: **partially novel** — novel on the prediction target (forward completeness spine), with
named adjacent lineages to cite (CROSSMINER, CPDP, JIT-SDP/Tabassum TSE 2022 premise validation,
Levin & Yehudai, Fujitsu patent US10521224). Key methodological debt it surfaced: re-run measure.py
lift against a MATTER-style *generic* checklist baseline, not just the adjacent-domain null.

Research gaps identified for the feature/bug-fix layers (not yet built): target-side JIT defect
signals (churn×category), issue-tracker lens, temporal ordering of categories (when gaps bite),
SZZ fix→origin linkage, severity weighting of clusters.

## ⏩ Session-2 update: completeness is THREE layers (the backtest ran)

The decisive backtest finally ran (dexto/Saiki, uncontaminated, blind: early demo → 146 later
feat/fix as answer key). It reframed everything.

- **The adaptive engine scored recall 0.42** → gate blocked → claim "falsified" *for that target*.
  But classifying the 146-item answer key showed **why**: 46% robustness / 34% new product features /
  21% churn. The engine recalled ~all of the robustness and ~none of the features — it was scored
  against a target it wasn't built for. **0.42 was a target mismatch, not a ceiling.**
- **The second-85% decomposes into three layers, each with its own predictor:**
  1. **Robustness** (hard-20% of what you built) → intent-derivation (`completeness.flow.js`) +
     recurring-fix mine (`cluster_fixes.py`). *Predictable.*
  2. **Generic scope** (features a full product of category X converges on) → **feature-surface mine**
     (`lens_mine.py`): *find* the feature set from mature neighbors. A feature spine mined from
     aider/OI/gptme recalled ~10 of the feature clusters (multi-provider, WebUI, plugins, auth,
     cost, install, GitHub) the robustness engine missed entirely. *Predictable by "go find it".*
  3. **Project-specific direction** (multimodal, subagents/A2A, vertical agents) → **not predictable,
     deliberately out of scope.** That's product strategy, not completeness; a completeness tool
     should name it as out of scope, not pretend to predict it.
- **Mining is now lens-parameterized** (`mine_common.py` substrate). An axis = a lens
  (recurring-fix → robustness; feature-surface → scope). New dimensions (integration / threat /
  operability surface) are a new `LENS` entry, not new plumbing. (Earned design call: the user
  predicted future dimensions; the lens registry is the seam for them.)
- **Dogfood loop closed.** `find_neighbors` classified 2080 as `ai-codebase-gap-analysis`; mining 5
  neighbors (kodus-ai, CodeGPT, sourcery, semgrep, sonarqube) gave a 14-capability scope spine;
  `check.py` against it flagged 3 real gaps (custom-rules, quality-gates, reporting) — which building
  `check.py` itself then **closed** (it IS the gate + reporting, and `--spine` IS custom rules).
  Re-running the gate now shows only 3 remaining (provider-selection, BYOK cost, CI/CD).
- **`check.py` keystone.** `2080 check <target> --spine <checklist>` = the product gate: runs
  `diff_target`'s assessment, blocks (exit 3) on applicable required gaps, human + `--json` report,
  CI-ready via exit code. **CI-ready ≠ has CI** — no workflow ships yet.
- **`diff_target` N/A broadened**: cross-MECHANISM categories (line-review, static scanning,
  multi-language, supply-chain on a prior-art/LLM tool) now mark `na_by_design`, so the gate doesn't
  fire on capabilities that are a different engine's job.

### Controlled measurement — `measure.py` (the numbers, finally trustworthy)

A bare recall number is uninterpretable: a lenient judge against a broad category list "matches"
almost anything (an early run scored the supposed-zero `direction` layer at **0.87**). So `measure.py`
reports **recall LIFT = recall(real spine) − recall(NULL spine)**, hybrid signal, per layer, across
targets OUTSIDE both spine pools (dexto/goose/cline — no leakage):
- **ML (deterministic):** abstract each answer-key item → phrase (`abstract_via_fan`), embed (all-MiniLM),
  recall = frac within cosine threshold of the spine. (Raw-subject embedding fails — vocabulary mismatch,
  the exact `cluster_fixes` lesson; abstraction first is mandatory.)
- **fan (conceptual):** J STRICT single-best-match judges ("name the ONE category this is a direct
  INSTANCE of, or null"), parallel via `fan`.
- **NULL control:** judge the same items against an adjacent-domain spine. Default synthetic 3d-game;
  better = a *real mined* spine via `--null-spine` (tmux+zellij → `terminal-multiplexer.features.json`).

**Result (strict 2-judge, n=3, tmux/zellij null, SUB-TYPE-MATCHED spines):**
robustness lift **0.44**, scope lift **0.42** — symmetric.
- null ≈ 0.01 (robustness) / 0.07 (scope) — non-zero for the right reason (multiplexers share generic
  plugins/config/session features) → the control is sensitive, not vacuous.
- **Stable across nulls:** scope lift was 0.47 (3d-game) / 0.44 (tmux-zellij) — moved ~0.03.
- **Strict + control ≈ halves the lenient numbers** (lenient was 0.54 / 0.72): leniency inflated ~2×.
- **Spine sub-type match is LOAD-BEARING (measured).** With a robustness spine mined from coordination
  tools (rally/build-loop/voltagent/symphony — wrong sub-type for agent-CLIs), robustness lift was only
  **0.23**. Re-mining it from agent-CLI neighbors (aider/OI/gptme → `ai-agent-cli.robustness.json`)
  **doubled it to 0.44**. So a mismatched spine roughly halves recall — the app-type-relativity thesis,
  now empirical, not asserted. The two engines are then symmetric (~0.43 each).
- ML lift is a weak conservative confirmer (~0.17 robustness; ~noise for scope) — the strict LLM judge
  is the primary instrument.

Honest headline: **2080 surfaces a measured ~40–45% of a project's second-85% on day 1** (both layers,
strict, controlled, n=3) — *provided the spine matches the target's sub-type*. Next rigor steps if
wanted: more targets + repeats for a variance bound; a same-sub-type scope spine sanity check.

Below is the session-1 framing (still accurate; the above refines "what completeness means").

---

## What 2080 is (evolved well beyond the original thesis)

2080 surfaces the **second-85%** — the hidden, required-but-absent work a demo hides — on day 1.
It attacks the problem from **two complementary directions**, plus a completion gate.

**Origin insight** (`gap_enum.md` + `gap_review.md` — the logout-button thesis test): a competent
first-pass gap list *itself has an invisible 20%*. Codex enumerated ~21 client-side gaps; the
review added ~13 deeper server-side/SSO/teardown/operability ones a demo never surfaces. The core
challenge 2080 must solve: **make the deep-half enumeration systematic, not dependent on a sharp
reviewer noticing SSO is absent.** Both engines below are attempts at exactly that.

## The two engines

### 1. Prior-art transfer (Python pipeline — VALIDATED this session)
*What did similar mature repos already have to add?* Mine their history, cluster, diff your repo.

`find_neighbors.py` (metatool: intent → discover+justify similar mature repos via gh REST API +
gpt-5.5; maturity **measured** from commit-count/age) → harvest (`harvest-gather-*.py` / rally-flow
flows) → `cluster_fixes.py` (LLM-abstract each commit→category-phrase via `fan`/gpt-5.5-low →
embed all-MiniLM cached → DBSCAN eps=0.34/cosine → tiered categories; `substantive` flag drops slop)
→ `checklists/<app-type>.json` (required=recurring / optional=project-specific, with day-1 tells) →
`diff_target.py` (assess a target's coverage; sub-type-aware N/A; deterministic citation check).

### 2. Adaptive intent-derivation (`completeness.flow.js` — rally-flow consumer, self-falsifying)
*What does this intent imply?* For the project-specific residual prior-art can't reach.
Phases: Orient → Derive (3 parallel: corpus-priors / intent / integration-ops) → Search (eval
dimensions vs the day-1 artifact, batched + looped) → **Refute** (loop-until-dry: "what dimension is
unexamined?") → **Score** (recall vs a harvest answer key) → **Gate** (refuses "done" unless coverage
holds; *with an answer key, requires recall ≥ 0.6 or it declares the adaptive-search claim
falsified*). Cross-harness via rally-flow.

## Key findings (hard-won)

- **Categories are app-type-relative; there is no universal checklist.** v1 = `ai-agent-tool`,
  validated cross-author + cross-language (rally/Rust, build-loop/TS, voltagent/TS [diff author],
  symphony/Elixir [OpenAI]). pirates (3d-game) fully disjoint; sweep (generic CLI) shared only the
  generic layer. The **metatool generalizes per-domain** by building the neighbor set on demand.
- **Recurrence ≈ 50% commit-weighted (measured, tuned)** — but that's **endpoint-convergence**
  (how much mature tools' category sets overlap), NOT forward prediction. The forward number is the
  **backtest: prior-art-diff predicts ~40% of engineering-debt** (the recurring infra-boundary
  skeleton: telemetry, persistence, run-identity, retry, input-validation, secret-guard,
  workspace-safety) and is **blind to product-direction + project-specific churn**.
- **Prior-art-diff is a recurring-infra-boundary detector, not a roadmap oracle.** It surfaces the
  predictable skeleton (~20% of all later work) on day 1; the rest needs engine #2 or is unpredictable.
- **AI-authorship ≠ slop.** build-loop is 88% AI-co-authored and was the *richest* corpus.
  Filtering by AI-trailer is counterproductive + low-recall (voltagent 0.6%). Slop is handled
  structurally (recurrence) + a `substantive` flag in the abstraction pass.
- **Naive ML failed; the hybrid works.** Embedding raw commits clusters by *project vocabulary*
  (~88% noise). LLM-abstraction (commit→category-phrase) THEN embed+cluster gives real categories.
- **Measured > guessed** everywhere: maturity (gh commit-count/age), recurrence (cluster metric),
  eps (sweep knee 0.34, catch-all-free). Earlier ~55-70% recurrence figures were catch-all-inflated.
- **Prompt-injection posture:** real surface (external repo text → LLM prompts) but bounded to
  analysis-integrity — no LLM→action, stateless calls, human-reviewed. Safe while analysis-only +
  human-approves-neighbors. An unattended "neighbor watch" would erode that — not built, not planned.

## Stack
Python + `uv` inline deps; `sentence-transformers` + `scikit-learn` DBSCAN (local all-MiniLM,
content-hash phrase cache); LLM calls through `mine_common.fan_batch` — native OpenAI-compatible
HTTP backend by default (BYOK), a local `fan` parallel-LLM CLI auto-used as accelerator when on
PATH (`gpt-5.5` reasoning-low, 16-wide, ~cents/run); `gh` REST API (not `gh search` — that
returned junk).
rally-flow (a separate local product) hosts `completeness.flow.js` and the JS
validation spikes (harvest/prior-art-diff/backtest/recurrence flows) — superseded by the Python
pipeline for harvest/cluster/diff; keep as historical or archive.

## Current state — working, dogfooded
The prior-art pipeline runs end-to-end and was dogfooded on 2080 itself — it found a **real gap:
no retry on transient `fan`/`gh` calls** (which we empirically hit this session). The adaptive
engine is built with a self-falsifying answer-key gate but its recall has not yet been measured.

## The decisive next test (the harness already exists)
**Run `completeness.flow.js` with a real answer key** (a harvested repo's later feat/fix work);
check recall ≥ 0.6. This is the validity test for the *adaptive* half — the experiment repeatedly
called "unbuilt" is in fact built, with falsification baked in. High recall → 2080 reaches the
project-specific residual; low recall → 2080 leans on the prior-art ~40% skeleton.

Other next steps: adversarial-verify pass for `diff_target` (catch prose-level over-claims); fix
2080's own retry gap; thicken the corpus with more other-author neighbors; tune maturity thresholds
(commit-count should override youth); **add an `assess_target` arm to the axis-promotion
criterion** — the lift/specificity controls run measure.py's embedding+judge protocol over spine
categories and certify *spine predictiveness*, not *gate adjudication accuracy*; the two are
disjoint code paths (measure.py never imports diff_target), so an axis can earn promotion while
the gate misjudges it. Either add a diff_target-based arm to measure.py or promote the
measure_recall.py protocol (which does exercise assess_target) with leave-one-out spines + more
repos. (Surfaced by the 2026-06-11 dual-model review; see the VALIDATED_GATING_AXES note in
check.py.)

## Files (refreshed 2026-06-11 — see `./2080 --json` for the live command map)
- `2080` — dispatcher: init / check / emit / mine / surface / threat / neighbors / measure / recall
- `mine_common.py` — shared mine substrate (native BYOK backend + optional fan accelerator, JSON extraction)
- `find_neighbors.py` — metatool: intent → justified neighbors (measured maturity)
- `init.py` — one command: neighbors → blob-less clones (`~/.cache/2080/`) → harvests → matched spines
- `lens_mine.py` — **the LLM lens registry** (feature/robustness/issue/discussions/config/test/docs-surface) + `merge_baseline` (gating-floor merge)
- `surface_mine.py` — deterministic operability lens, 16 probes + content-hit hygiene (no LLM)
- `threat_mine.py` — deterministic SECURITY lens: neighbor deps → OSV → vulnerability-class spine
- `diff_target.py` — evidence-grounded coverage assessment (per-category git-grep retrieval, synonym escalation, fix_sites)
- `check.py` — **keystone gate**: blocks (exit 3) on applicable required gaps; `VALIDATED_GATING_AXES = {SCOPE, ISSUES}` (TESTS demoted same-day by the specificity control); battery mode; `--save/--from-assessment` split
- `emit.py` — blocking gaps → agent-ready task queue (acceptance = day1_tell, verify_cmd per task)
- `measure.py` — controlled recall-lift instrument (prepare-once-judge-N fast path; also hosts embed/abstract from the archived cluster mine)
- `measure_recall.py` — gate recall vs a neighbor's own future (snapshot backtest)
- `checklists/generic-software.baseline.json` — **FROZEN measurement control** (20 categories; do not edit)
- `checklists/generic-software.floor.json` — **gating floor**: industry-curated superset (Scorecard/Badge/community-profile), what `merge_baseline` and batteries use
- `checklists/terminal-multiplexer.features.json` — adjacent-domain NULL control (tmux+zellij)
- `hooks/stop_gate.sh` + `.github/workflows/2080-gate.yml` — Stop-hook and CI consumers of saved assessments (`docs/INTEGRATIONS.md`)
- `archive/` — retired primitives with pull-back conditions (`cluster_fixes.py`, `completeness.flow.js`)
- `docs/measurements/` — raw control-run JSONs behind every lift number quoted above
- `checklists/ai-agent-coordination.robustness.json` — robustness spine, COORDINATION sub-type (rally/build-loop/voltagent/symphony; was `ai-agent-tool.json` — renamed to kill the label collision with the aider/OI/gptme-derived `ai-agent-tool.features.json`)
- `checklists/ai-agent-cli.robustness.json` — robustness spine, agent-CLI sub-type (aider/OI/gptme) — the matched one
- `checklists/ai-agent-tool.features.json` — scope spine for ai-agent-tool (feature lens; aider/OI/gptme)
- `checklists/ai-codebase-gap-analysis.features.json` — **2080's OWN scope spine** (5 neighbors; the dogfood)
- `docs/gap_enum.md` / `docs/gap_review.md` — the logout thesis test (the origin insight)

Backtest details and scratch args live in `/tmp` clones (regenerable); `.backtest-*-args.json` are gitignored.
