#!/usr/bin/env python3
"""
test_cluster_eps.py — deterministic tests for cluster_fixes' corpus-tuned auto-eps.

The codified lesson: the DBSCAN eps knee is corpus-dependent (0.34 produced a coherent spine on
the agent-tool corpus but a 334-commit catch-all on the telegram corpus). pick_eps encodes the
selection rule so init.py and every future mine get it at 100% compliance, not HANDOFF-paragraph
compliance. Run: python3 test_cluster_eps.py
"""
from cluster_fixes import pick_eps


def row(eps, ms, recur, max_clust, clustered, sil):
    return {"eps": eps, "ms": ms, "n_clusters": 0, "noise_pct": 0.0, "recur_clusters": recur,
            "recur_commit_pct": 0.0, "max_clust": max_clust, "clustered": clustered, "silhouette": sil}


# the REAL telegram-corpus sweep (ms=2 rows, 2026-06-10) — the run that exposed the catch-all
TELEGRAM = [
    row(0.22, 2, 94, 11, 484, 0.667),
    row(0.26, 2, 115, 25, 608, 0.525),
    row(0.30, 2, 117, 143, 745, 0.288),
    row(0.34, 2, 97, 334, 897, 0.084),
    row(0.38, 2, 68, 708, 1044, -0.079),
    row(0.22, 3, 44, 11, 242, 0.633),  # ms=3 rows must be ignored
]


def test_telegram_corpus_picks_026_not_default_034():
    # intent: the live failure this codifies — at the 0.34 default the telegram spine's top
    # "category" was a 334-commit catch-all spanning unrelated fixes, inflating the required
    # count to 97 meaningless entries. Auto-eps must reproduce the human-tuned 0.26 choice.
    assert pick_eps(TELEGRAM) == 0.26


def test_catch_all_guard_rejects_giant_clusters():
    # intent: a max cluster >5% of clustered commits IS the catch-all shape; an eps that
    # produces one must never win regardless of how many recurring clusters it shows.
    rows = [row(0.30, 2, 200, 143, 745, 0.9),   # huge recurrence but catch-all -> banned
            row(0.22, 2, 50, 10, 400, 0.5)]
    assert pick_eps(rows) == 0.22


def test_fallback_when_nothing_passes_guards():
    # intent: on a degenerate corpus where every eps yields catch-alls or mush, the mine must
    # still run (best-silhouette fallback) rather than crash — init.py calls this unattended.
    rows = [row(0.30, 2, 10, 500, 700, 0.25), row(0.34, 2, 12, 600, 800, 0.10)]
    assert pick_eps(rows) == 0.30


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
