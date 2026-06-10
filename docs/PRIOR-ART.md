# Prior-art survey — cross-repo convergence mining as a forward completeness predictor

_Status: **VERIFIED** (2026-06-09). Deep-research run: 5 angles, 21 sources fetched, 102 claims
extracted, 25 adversarially verified (3 refuters per claim) → 22 confirmed, 3 killed, synthesized
to 8 findings. Verdicts below cite vote counts._

## Novelty verdict: **PARTIALLY NOVEL** (medium confidence)

No published work was found that uses cross-repo recurring fix/feature-category convergence as a
**forward predictor of a new project's remaining/required work**. 2080's novel dimension is the
*prediction target* (a day-1 completeness spine), not its mechanisms — every component has strong
adjacent prior art that any writeup must cite and position against.

"Confirmed novel" cannot be issued: two parts of the question produced no surviving verified
claims — (a) 2023–2026 LLM-era agentic completeness / spec-coverage / definition-of-done tooling,
and (b) commercial "what will this project still need" products. Those need a dedicated pass
(see Open questions). The verdict is an absence-of-evidence conclusion bounded by the surveyed
lineages.

## Closest works (verified)

1. **CROSSMINER** (Di Rocco et al., EMSE 2021) — architecturally closest: dedicated
   "cross-project miner" layer over OSS repos. Outputs are *artifacts* (similar projects,
   library recommendations via CrossRec, API snippets, README tags), reactive and IDE-integrated —
   not an abstracted remaining-work checklist. Verifiers specifically probed CrossRec as a
   counter-candidate; the distinction held (9-0). Full-text greps for completeness/remaining-work/
   checklist: zero hits.
2. **CPDP** (Herbold's EMSE mapping study; W-BDA+ 2024) — shares 2080's exact cold-start
   motivation verbatim ("lack of data... in the early stage of new software projects") but is
   strictly module-level binary defect classification over existing code (6-0). Adopt its
   **"strict CPDP"** framing: no target-history data in training — 2080's day-1 setting.
3. **JIT-SDP / CP-JIT-SDP** (ACM CSUR 2022 survey, 67 studies; Tabassum, Minku & Feng TSE 2022) —
   nearest methodological neighbor (12-0). **Tabassum TSE 2022 empirically validates 2080's core
   premise**: cross-project commit data improves early-stage prediction on new projects (G-mean
   up to +53.89 absolute). Caveats: "up to" best case; only 2 of 4 CP approaches beat
   within-project; sources weren't type-matched neighbors; target is defect-proneness. The
   premise validation is analogical, not direct.
4. **Levin & Yehudai** (PROMISE 2017) — nearest prior art for the commit-abstraction step:
   project-agnostic classification of commits into corrective/perfective/adaptive (76% acc
   cross-project), but 3 *fixed* classes vs 2080's mined open categories, and retrospective
   characterization, never a day-1 spine (9-0). (A claim that their classifier was
   keyword-matching-only was REFUTED 0-3 — they used ML over commit content; don't repeat it.)
5. **US Patent 10,521,224** (Fujitsu, granted 2019) — patented prior art for the
   neighbor-selection step: similarity scoring between subject and candidate projects for
   cross-project learning, via BM25 over static source features (9-0). No commit-history mining,
   no category clustering; downstream use is defect identification in an existing project.
   2080's convergence mining and completeness gating are outside the granted claims — but
   family continuations were NOT surveyed; freedom-to-operate is not established.
6. **Repo2Vec** (2021) — repo-embedding similarity (93% precision) usable for neighbor
   identification; no commit analysis, no forward prediction (3-0).

## Steal list — evaluation methodology (12-0, the load-bearing findings)

1. **Trivial/null baselines are mandatory and often win.** Herbold 2018 (26 CPDP approaches):
   "trivially assuming everything as defective is on average better than CPDP under cost
   considerations" — independently replicated by Zhou et al.'s ManualDown (TOSEM 2018, the
   peer-reviewed anchor; Herbold 2018 itself is a non-peer-reviewed preprint). For 2080: the
   spine must beat a generic "every project needs error handling" checklist, not just the
   adjacent-domain null spine. measure.py's lift (0.23→0.44) should be re-run against a
   ONE-style generic baseline under matched effort.
2. **Metric choice can completely reorder rankings.** Cost-metric rankings were uncorrelated
   (Kendall's τ = −0.047) with AUC/F1/G/MCC rankings. 2080 must justify raw recall vs
   recall-lift vs effort-weighted coverage as *the* metric, or report several.
3. **MATTER (2023)** is a directly stealable protocol template: one simple unsupervised global
   baseline (ONE), SQA-effort-aligned thresholds, unified core indicators.
4. **CP-JIT-SDP evaluation template**: many projects, strict chronological ordering, and a
   **verification-latency waiting period** before labeling (a category unaddressed for 6 months
   ≠ never needed).

## Open questions (next passes if pursued)

- LLM-era (2023–2026) agentic completeness tooling: do spec-coverage checkers / DoD gates /
  LLM-generated project checklists (Devin/SWE-agent/OpenHands ecosystems) anticipate the framing?
- Requirements-mining literature (app-store feature mining, cross-project issue mining, NFR
  extraction) — possibly a closer neighbor than CPDP/JIT-SDP for "recurring category spine as
  required scope."
- Patent family continuations of US10521224 (and IBM/Microsoft filings) for freedom-to-operate.
- Can 2080's recall-lift survive a MATTER-style generic-checklist control? The CPDP track record
  says this is a real risk, not a formality.

## Follow-up pass (2026-06-10, verified — 24 claims, all 3-0; the three open angles)

**Angle 1 — LLM-era agentic completeness tooling: NO anticipation (high confidence).**
OpenSpec, GitHub Spec Kit, and the "Kitchen Loop" preprint (arXiv 2603.25697) all gate
completeness against the project's OWN user-authored spec — zero neighbor-repo or commit-history
input anywhere (full-text greps verified). The Kitchen Loop even names "knowing what to build" as
the open bottleneck without solving it — the strongest signal 2080's gap is recognized but
unfilled in the 2026 agentic literature. Nearest academic line (Luitel et al., RE-J 2024) checks
completeness INSIDE a requirements document via BERT. Caveat: absence claim in a weekly-moving
space; Devin/SWE-agent/OpenHands/Cursor internals were covered only by searches failing to
surface anticipating mechanisms, not by direct inventory.

**Angle 2 — requirements mining: PARTIAL anticipation, and it IS the closer neighbor lineage.**
The conceptual move "recurring features across similar products = candidate scope for a new
product" is established prior art: Harman/Jia/Zhang (MSR 2012, app-store featurelets) founded it;
Xie et al. (JSS 2022) recommend MISSING standard features relative to similar products (from UI
pages); APPFIRE (ASE 2024) recommends features for a NEW app from a description (structurally the
closest pipeline); Iqbal et al. (2019) propose exactly 2080's day-1 input/output shape — as an
unimplemented vision paper. It's even documented manual PRACTICE (Al-Subaihin, TSE: 56% of 186
developers gather requirements from similar apps). **Position 2080 against THIS lineage, not
defect prediction.**

**Angle 3 — patents: UNANSWERED twice.** Zero patent claims survived verification in either pass.
No freedom-to-operate signal exists in any direction. Not legal advice; a human/professional
search is the only way to close this.

**Updated overall verdict: "partially novel" survives, narrowed.** Not novel: completeness gates
for agentic coding (all spec-internal); the idea of neighbor products as scope predictors
(app-store lineage). Novel residue, per verified evidence: (i) commit histories of mature
same-app-type repos as the evidence base, (ii) a recurring fix/feature CATEGORY spine as the
artifact, (iii) its use as a day-1 forward predictor AND enforcement gate for hidden remaining
work. Note this aligns with the measurement verdict: the scope layer (where 2080's lift survives
the generic-baseline control) is exactly where the app-store lineage stops short of commit-mined,
gate-enforced prediction.

## Killed claims (excluded — do not reuse)

- "Levin & Yehudai classify by keyword matching" (0-3).
- "Herbold's survey: 50 publications, all numeric-metric features" (1-2 — overgeneralized).
- "Herbold 2018 is the canonical benchmark protocol" (0-3 — it's an ICSE-rejected preprint;
  its baseline finding survives via Zhou et al. TOSEM 2018).
