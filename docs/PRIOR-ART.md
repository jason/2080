# Prior-art survey — cross-repo convergence mining as a forward completeness predictor

_Status: **INTERIM / UNVERIFIED** (2026-06-09). Deep-research run completed search + fetch
(5 angles, 20 sources, 98 claims extracted, top 25 selected) but the adversarial-verification
phase was killed by a session rate limit — every claim below is a single-pass extraction from
a fetched source, not a verified finding. Re-run verification via the workflow resume before
citing any of this externally._

## Provisional novelty verdict: **likely novel on the exact framing**

No surveyed work matches 2080's core: mining *recurring fix/feature categories across mature
same-app-type neighbors* and using that convergent category spine as a *forward predictor of a
new project's remaining required work* (completeness). The components have prior art; the
composition and the prediction target do not appear to.

Key negative signal: a 2026 survey of LLMs in Mining Software Repositories (85 primary studies,
2017–2025; arxiv.org/html/2604.00787v1) reportedly contains no work with this framing, and notes
forward *prediction* is among the least-populated MSR application types (classification 42.4% and
generation 28.2% dominate).

## Nearest neighbors (closest 5)

1. **Cross-Project Defect Prediction (CPDP)** — predicts *defect-proneness of existing modules*
   in a target project from other projects' metrics; never remaining work / feature scope.
   Useful: the field formalizes 2080's day-1 constraint as **"strict CPDP"** (no target-history
   training data) — adopt the strict/mixed/MPDP taxonomy to position 2080's evaluation setting.
   (Mapping study of 50 publications 2002–2015: arxiv.org/pdf/1705.06429)
2. **Cross-project just-in-time defect prediction (CP-JIT-SDP)** — same *cold-start motivation*
   (new project, no history), different target (defect-inducing commits). Reported result:
   cross-project data improved early-stage G-mean by up to ~54 points over within-project-only —
   evidence that neighbor-repo history carries forward-predictive signal, 2080's core premise.
   (researchgate.net/publication/358513763)
3. **CROSSMINER (EMSE 2021)** — cross-project mining for *artifact recommendation during
   implementation* (libraries, snippets, similar projects), not completeness prediction.
   (link.springer.com/article/10.1007/s10664-021-09963-7)
4. **MATTER / trivial-baseline critique (arxiv.org/pdf/2302.00394)** — under effort-aware
   evaluation, most recent defect predictors fail to beat a trivial size-based baseline (ONE);
   a benchmark of 26 CPDP approaches (arxiv.org/pdf/1801.04107) similarly found "flag everything"
   beat all 26 under cost metrics. Lesson: lift claims are illusory without null/trivial controls.
   2080's null-spine recall-lift design is aligned with this — keep it mandatory.
5. **LLM commit classification** — exists but sparse (4 of 36 LLM-MSR classification studies
   target commits) and descriptive: e.g. 680k+ commits across 100k Hugging Face repos classified
   into a *fixed* taxonomy (arxiv.org/pdf/2411.09645), not open-vocabulary abstraction feeding a
   forward predictor. 2080's abstract-then-cluster (open categories) differs.

## Steal list (methods / eval protocols)

- **Strict-CPDP framing** for the measurement writeup: 2080 evaluates under "strict" conditions
  (no target history in the spine). Name it that.
- **CP-JIT-SDP evaluation template**: many projects (Commit Guru–style harvesting), strict
  chronological ordering by author timestamp, and a **verification-latency waiting period**
  before labeling work "not needed" (a category absent for 6 months ≠ never needed).
- **Effort-aware lift metrics**: recall@20%-inspection-effort and Popt (PLOS ONE
  10.1371/journal.pone.0211359) — adapt as "recall at top-N spine categories," which matches how
  a team actually consumes the checklist.
- **Trivial baseline discipline (MATTER)**: alongside the null-spine control, add a trivial
  baseline (e.g. a generic "any software project" checklist) — beat both before claiming lift.

## Open verification TODO

Resume the deep-research workflow's verify phase (resumeFromRunId wf_17982ec7-5af; search/fetch
results are cached) to adversarially check the 25 claims, especially the two load-bearing ones:
the 2026 LLM-MSR survey's coverage claim, and the strict-CPDP taxonomy mapping.
