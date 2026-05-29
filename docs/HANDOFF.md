# 2080 — Handoff

_Last updated: 2026-05-29 (session 2)_

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
     (`feature_mine.py`): *find* the feature set from mature neighbors. A feature spine mined from
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
Python + `uv` inline deps; `sentence-transformers` + `scikit-learn` DBSCAN (reused from
`~/projects/tools/corrections/cluster_embedding.py`); `gpt-5.5` low via `fan` (provider
`openai-codex`, ~10 parallel calls/run, ~cents); `gh` REST API (not `gh search` — that returned junk).
rally-flow (`~/projects/rally-flow`, separate product) hosts `completeness.flow.js` and the JS
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
- `feature_mine.py` — **feature-surface lens** → scope spine (README + `feat:` → convergent capability spine; `--lens` is the extension seam)
- `diff_target.py` — target coverage diff; importable `assess_target()`; N/A now covers cross-mechanism
- `check.py` — **keystone gate**: `2080 check <target> --spine <checklist>` → blocks (exit 3) on required gaps; CI-ready
- `completeness.flow.js` — adaptive intent-derivation engine (run on rally-flow, `--harness fan`)
- `checklists/ai-agent-tool.json` — robustness spine (recurring-fix lens; 15 required + 20 optional)
- `checklists/ai-agent-tool.features.json` — scope spine for ai-agent-tool (feature lens; aider/OI/gptme)
- `checklists/ai-codebase-gap-analysis.features.json` — **2080's OWN scope spine** (5 neighbors; the dogfood)
- `gap_enum.md` / `gap_review.md` — the logout thesis test (the origin insight)

Backtest details and scratch args live in `/tmp` clones (regenerable); `.backtest-*-args.json` are gitignored.
