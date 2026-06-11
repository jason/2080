# archive/

Retired primitives, kept for the scale at which they'd be right again.

## cluster_fixes.py + test_cluster_eps.py (archived 2026-06-11)

The original robustness mine: LLM-abstract each fix commit → phrase, embed (all-MiniLM),
DBSCAN-cluster with corpus-tuned eps, tier by cross-project recurrence.

**Why archived** (interleaved ×3 control, measure.py, same targets/conditions):

| spine | robustness lift vs generic baseline | absolute recall |
|---|---|---|
| cluster_fixes (change-shaped labels) | −0.20 ±0.04 | 0.46–0.51 |
| lens_mine robustness-surface (capability-phrased) | **−0.04 ±0.02** | **0.59–0.64** |

The one-call synthesis lens matches baseline-parity with no embedding stack, and its labels are
judgeable capabilities instead of change-shaped cluster names. `merge_baseline` (the gating
floor) moved to lens_mine.py; `embed`/`abstract_via_fan` moved to measure.py (last consumer).

**Pull this back when**: a corpus is too large for single-call synthesis (thousands of
commits across many neighbors) and you need the scalable abstract→embed→cluster pipeline, or
you want the eps sweep / recurrence-percentage instrumentation for a measurement.

## completeness.flow.js (archived 2026-06-11)

The session-1 adaptive intent-derivation engine (rally-flow consumer, self-falsifying
answer-key gate). Superseded by the Python pipeline for everything it did; its decisive
"run with a real answer key" experiment was overtaken by measure.py's controlled-lift
protocol, and the session-2 backtest showed its target (project-specific direction) is
deliberately out of scope.

**Pull this back when**: attacking the project-specific-direction layer ever becomes
in-scope and you want the refute-loop/score/gate phase structure as a starting skeleton.
