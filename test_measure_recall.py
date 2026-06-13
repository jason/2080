#!/usr/bin/env python3
"""
test_measure_recall.py — deterministic tests for measure_recall's pure layer.

No LLM, no git: exercises split_at / agreed_mappings / ground_truth / recall_of_run on
synthetic data. Run: python3 test_measure_recall.py
"""
from measure_recall import (split_at, sample_even, agreed_mappings, ground_truth,
                            recall_of_run, judge_future_calls, precision_of_run)

CATS = [{"category": "Plugin marketplace/extensions"}, {"category": "Web dashboard"},
        {"category": "Multi-channel adapters"}]


def test_split_newest_first_future_before_snapshot():
    # intent: harvests are newest-first; getting the direction wrong would build ground truth
    # from the repo's PAST (already present at snapshot) and report recall against nonsense.
    commits = [{"sha": f"s{i}", "subject": f"c{i}"} for i in range(100)]
    future, snap = split_at(commits, 0.25)
    assert len(future) == 75 and snap == "s75"  # 25% happened; commits[0..74] are the future


def test_split_extremes_never_empty():
    # intent: frac 0.0/1.0 (user typo or tiny harvest) must not produce an empty future or an
    # out-of-range snapshot index — both would crash or silently measure nothing.
    commits = [{"sha": f"s{i}", "subject": ""} for i in range(10)]
    f0, s0 = split_at(commits, 0.0)
    f1, s1 = split_at(commits, 1.0)
    assert 1 <= len(f0) <= 9 and 1 <= len(f1) <= 9 and s0.startswith("s") and s1.startswith("s")


def test_sample_even_spans_whole_future():
    # intent: a 2700-commit future judged only at its newest end would rebuild the v0.1
    # contamination (mature-era commits only); the sample must reach both ends of the future.
    commits = [{"sha": f"s{i}", "subject": ""} for i in range(2700)]
    s = sample_even(commits, 400)
    assert len(s) == 400 and s[0]["sha"] == "s0" and int(s[-1]["sha"][1:]) > 2600
    assert sample_even(commits[:300], 400) == commits[:300]  # under cap: untouched


def test_agreement_requires_all_judges_same_category():
    # intent: a single hallucinating judge must not put a category into ground truth — the
    # whole recall number inherits the ground truth's noise floor.
    calls = [{"id": "recall|0|0", "_chunk_start": 0, "_n": 2},
             {"id": "recall|0|1", "_chunk_start": 0, "_n": 2}]
    results = {"recall|0|0": '{"1": {"cat": "Web dashboard"}, "2": {"cat": "Web dashboard"}}',
               "recall|0|1": '{"1": {"cat": "Web dashboard"}, "2": {"cat": null}}'}
    m = agreed_mappings(calls, results, judges=2)
    assert m == {0: "web dashboard"}  # commit 2: judges disagreed (cat vs null) -> dropped


def test_ground_truth_needs_recurring_commits_and_real_labels():
    # intent: one-off mappings and judge-invented labels must not become ground truth; a fake
    # category can never be flagged by the assessor, so it would read as a phantom miss.
    mappings = {0: "web dashboard", 1: "web dashboard", 2: "plugin marketplace/extensions",
                3: "made-up category", 4: "made-up category"}
    assert ground_truth(mappings, CATS, min_commits=2) == ["web dashboard"]


def test_recall_counts_flagged_and_names_misses_with_verdict():
    # intent: the deliverable is WHICH upcoming work the gate missed and what it wrongly said
    # ('covered' = blind spot); losing the per-miss verdict would make the number unactionable.
    gt = ["web dashboard", "multi-channel adapters", "plugin marketplace/extensions"]
    assessment = {"categories": [
        {"category": "Web dashboard", "status": "gap"},
        {"category": "Multi-channel adapters", "status": "covered"},
        {"category": "Plugin marketplace/extensions", "status": "partial"}]}
    rec, misses = recall_of_run(gt, assessment)
    assert abs(rec - 2 / 3) < 1e-9
    assert misses == {"multi-channel adapters": "covered"}


def test_judge_calls_chunk_and_replicate_per_judge():
    # intent: each chunk must be judged by ALL J judges with identical prompts — fewer
    # replicas silently weakens the agreement filter to a single judge's word.
    future = [{"sha": f"s{i}", "subject": f"add thing {i}"} for i in range(20)]
    calls = judge_future_calls(future, CATS, judges=2)
    assert len(calls) == 4  # 2 chunks (18 + 2) x 2 judges
    assert calls[0]["prompt"] == calls[1]["prompt"] and calls[0]["id"] != calls[1]["id"]


def test_blocking_precision_future_wins_and_dormant_past_is_false_block():
    # intent: the promotion bar's third arm. Two miscounts would let a miscalibrated axis earn
    # gating power: (a) a partial on a category the repo kept building (its own admission of
    # inadequacy) scored as false block — that's the gate's CORRECT core behavior under
    # fail_on=partial; (b) a block on the repo's own 'done' list (built before, dormant after)
    # scored as right — that's the real false block, and it must also drive false_block_rate.
    assessment = {"categories": [
        {"category": "Web dashboard", "tier": "required", "status": "gap"},          # future built: RIGHT
        {"category": "Multi-channel adapters", "tier": "required", "status": "partial"},  # past AND future: RIGHT (future wins)
        {"category": "Agent command system", "tier": "required", "status": "partial"},    # past only, dormant: WRONG
        {"category": "Plugin marketplace/extensions", "tier": "required", "status": "gap"},  # nobody built: UNVERIFIED
        {"category": "Covered thing", "tier": "required", "status": "covered"},      # not flagged
        {"category": "Optional thing", "tier": "optional", "status": "gap"},         # optional never counts
    ]}
    gt_future = ["web dashboard", "multi-channel adapters"]
    covered_past = {"multi-channel adapters", "agent command system", "unflagged adequate thing"}
    b = precision_of_run(gt_future, covered_past, assessment)
    assert b["right"] == ["multi-channel adapters", "web dashboard"]
    assert b["wrong"] == ["agent command system"]
    assert b["unverified"] == ["plugin marketplace/extensions"]
    assert b["flagged"] == 4 and b["adjudicated"] == 3 and b["precision"] == 0.667
    # adequate set = {agent command system, unflagged adequate thing}; 1 of 2 falsely blocked
    assert b["n_adequate"] == 2 and b["false_block_rate"] == 0.5
    none_adj = precision_of_run([], set(), assessment)
    assert none_adj["precision"] is None  # 0 adjudicable must be n/a, never a fake 1.0 or 0.0
    assert none_adj["false_block_rate"] is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
