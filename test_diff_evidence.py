#!/usr/bin/env python3
"""
test_diff_evidence.py — deterministic tests for diff_target's fix_sites evidence layer.

No LLM calls: exercises validate_fix_sites / apply_assessments on synthetic assessments
against a fake fileset. Run: python3 test_diff_evidence.py
"""
from diff_target import validate_fix_sites, apply_assessments

FILESET = {"app.py", "cli.py", "store.py"}


def test_hallucinated_fix_site_dropped_and_flagged():
    # intent: an LLM-invented file path would send the fixing agent to edit a file that
    # doesn't exist — hallucinated sites must be dropped and the category flagged.
    kept, dropped = validate_fix_sites(
        [{"file": "app.py", "what": "add retry wrapper"},
         {"file": "made_up/handler.py", "what": "add webhook"}], FILESET)
    assert kept == [{"file": "app.py", "what": "add retry wrapper"}]
    assert dropped is True


def test_all_real_fix_sites_kept_unflagged():
    # intent: valid evidence must survive validation untouched — over-aggressive dropping
    # would strip the WHERE-to-act signal the whole feature exists to provide.
    kept, dropped = validate_fix_sites(
        [{"file": "cli.py", "what": "add --json"}, {"file": "store.py", "what": "add migration"}], FILESET)
    assert [s["file"] for s in kept] == ["cli.py", "store.py"]
    assert dropped is False


def test_malformed_and_empty_fix_sites_safe():
    # intent: model output is untrusted JSON — None, non-dict entries, or missing keys must
    # not crash assessment (a crash here loses the whole paid LLM verdict).
    assert validate_fix_sites(None, FILESET) == ([], False)
    kept, dropped = validate_fix_sites(["app.py", {"what": "no file key"}, 42], FILESET)
    assert kept == [] and dropped is True


def test_gap_and_partial_always_carry_fix_sites_keys():
    # intent: check.py/emit.py rely on fix_sites + fix_sites_unverified existing on every
    # gap/partial — a missing key would KeyError downstream consumers at gate time.
    cats = [{"category": "A", "tier": "required"}, {"category": "B", "tier": "required"},
            {"category": "C", "tier": "optional"}]
    assessments = [
        {"n": 1, "status": "gap", "reasoning": "missing", "cited_files": []},  # no fix_sites returned at all
        {"n": 2, "status": "partial", "reasoning": "half", "cited_files": [],
         "fix_sites": [{"file": "ghost.py", "what": "x"}]},
        {"n": 3, "status": "covered", "reasoning": "ok", "cited_files": ["app.py"]},
    ]
    out = apply_assessments(cats, assessments, FILESET)
    assert out[0]["fix_sites"] == [] and out[0]["fix_sites_unverified"] is False
    assert out[1]["fix_sites"] == [] and out[1]["fix_sites_unverified"] is True
    assert "fix_sites" not in out[2]  # covered: cited_files remain the proof, no fix_sites key


def test_cited_files_validation_unchanged():
    # intent: regression guard — adding fix_sites must not break the existing cited_files
    # anti-hallucination contract that check.py's verdict surfaces as citation_unverified.
    cats = [{"category": "A", "tier": "required"}]
    out = apply_assessments(cats, [{"n": 1, "status": "covered", "cited_files": ["nope.py"]}], FILESET)
    assert out[0]["citation_unverified"] is True and out[0]["status"] == "covered"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
