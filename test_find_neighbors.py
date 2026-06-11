#!/usr/bin/env python3
"""
test_find_neighbors.py — deterministic tests for find_neighbors' maturity attachment.

No network, no LLM: maturity measurement is injected. The live gh/fan path is exercised
by real init runs. Run: python3 test_find_neighbors.py
"""
import time

from find_neighbors import attach_maturity


def test_attach_maturity_results_stay_aligned_under_concurrency():
    # intent: maturity is measured CONCURRENTLY (one gh round-trip per neighbor) and is the
    # ranking key for which repos get cloned and mined — a result landing on the wrong
    # neighbor silently re-ranks the proposal toward the wrong prior art. Slow-first /
    # fast-second forces a swap if alignment ever depends on completion order.
    neighbors = [{"repo": "a/slow"}, {"repo": "b/fast"}, {"repo": "c/unsearched"}]
    by_name = {"a/slow": {"full_name": "a/slow"}, "b/fast": {"full_name": "b/fast"}}

    def measure(cand):
        if cand["full_name"] == "a/slow":
            time.sleep(0.05)
            return {"label": "high", "commits": 500}
        return {"label": "med", "commits": 60}

    out = attach_maturity(neighbors, by_name, measure=measure)
    assert out[0]["maturity"]["commits"] == 500   # the slow result still lands on a/slow
    assert out[1]["maturity"]["commits"] == 60
    # a neighbor the candidate search never returned can't be measured — it must surface as
    # unknown/0 commits (sorts last) instead of crashing the proposal
    assert out[2]["maturity"] == {"label": "unknown", "commits": 0}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
