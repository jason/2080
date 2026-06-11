# 2080 — Handoff

_Last updated: 2026-06-10 (session 5)_

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
(commit-count should override youth).

## Files
- `mine_common.py` — shared mine substrate (fan call + JSON extraction); the "mine family" base
- `find_neighbors.py` — metatool: intent → justified neighbors (measured maturity)
- `cluster_fixes.py` — **recurring-fix lens** → robustness spine (LLM-abstract + embed + DBSCAN + tiered emit)
- `lens_mine.py` — **feature-surface lens** → scope spine (README + `feat:` → convergent capability spine; `--lens` is the extension seam)
- `diff_target.py` — target coverage diff; importable `assess_target()`; N/A now covers cross-mechanism
- `check.py` — **keystone gate**: `2080 check <target> --spine <checklist>` → blocks (exit 3) on required gaps; CI-ready
- `measure.py` — **controlled recall measurement**: ML + strict-fan judges, recall LIFT over a null spine (`--null-spine`)
- `checklists/terminal-multiplexer.features.json` — the real adjacent-domain NULL control (tmux+zellij)
- `completeness.flow.js` — adaptive intent-derivation engine (run on rally-flow, `--harness fan`)
- `checklists/ai-agent-coordination.robustness.json` — robustness spine, COORDINATION sub-type (rally/build-loop/voltagent/symphony; was `ai-agent-tool.json` — renamed to kill the label collision with the aider/OI/gptme-derived `ai-agent-tool.features.json`)
- `checklists/ai-agent-cli.robustness.json` — robustness spine, agent-CLI sub-type (aider/OI/gptme) — the matched one
- `checklists/ai-agent-tool.features.json` — scope spine for ai-agent-tool (feature lens; aider/OI/gptme)
- `checklists/ai-codebase-gap-analysis.features.json` — **2080's OWN scope spine** (5 neighbors; the dogfood)
- `docs/gap_enum.md` / `docs/gap_review.md` — the logout thesis test (the origin insight)

Backtest details and scratch args live in `/tmp` clones (regenerable); `.backtest-*-args.json` are gitignored.
