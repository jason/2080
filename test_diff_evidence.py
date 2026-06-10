#!/usr/bin/env python3
"""
test_diff_evidence.py — deterministic tests for diff_target's fix_sites evidence layer.

No LLM calls: exercises validate_fix_sites / apply_assessments on synthetic assessments
against a fake fileset. Run: python3 test_diff_evidence.py
"""
from diff_target import (validate_fix_sites, apply_assessments, category_keywords,
                         rank_evidence_files, build_dir_map, evidence_candidate,
                         clean_synonym_terms, merge_escalation)

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


def test_category_keywords_keep_domain_words_drop_change_words():
    # intent: searching a repo for "fix"/"improvement" matches everything and grounds nothing —
    # the precision failure (0.083 on goose) came from ungrounded verdicts. Keywords must be
    # the capability's domain words only, deduped across category + aliases.
    kws = category_keywords({"category": "error handling improvement",
                             "aliases": "error handling improvement / exception classification"})
    assert kws == ["error", "exception", "classification"]


def test_rank_evidence_drops_too_generic_keyword():
    # intent: a keyword hitting most of the repo (e.g. "error" in a vendored lockfile world)
    # would rank every file equally and bury the real evidence — it must be discarded.
    hits = {"telemetry": {"src/obs.py"},
            "config": {f"f{i}.py" for i in range(60)}}  # 60% of a 100-file repo
    assert rank_evidence_files(hits, nfiles=100) == ["src/obs.py"]


def test_rank_evidence_prefers_multi_keyword_files():
    # intent: the file matching several of the category's terms is where the capability lives;
    # ranking it below single-term matches would point the assessor at the wrong evidence.
    hits = {"retry": {"net.py", "client.py"}, "backoff": {"client.py"}}
    assert rank_evidence_files(hits, nfiles=100)[0] == "client.py"


def test_dir_map_summarizes_shape_not_alphabetical_order():
    # intent: the old first-80-alphabetical file list showed .github/ as "the app" on large
    # repos; the dir map must rank directories by file count so the real source dominates.
    files = [f"crates/core/src/m{i}.rs" for i in range(50)] + [".github/workflows/ci.yml", "README.md"]
    m = build_dir_map(files)
    assert m.splitlines()[0] == "crates/core/ (50 files)"
    assert ".github" in m  # still visible, just not first


def test_evidence_candidates_exclude_vendored_blobs():
    # intent: on goose, pnpm-lock.yaml / mermaid.min.js / whisper_data tokens matched every
    # keyword and outranked real source — verdicts grounded in junk evidence are the 0.083
    # precision failure recurring in a new disguise. Blobs must never be evidence.
    assert evidence_candidate("crates/goose-cli/src/session/mod.rs")
    assert evidence_candidate("docs/error-handling.md")
    assert not evidence_candidate("ui/pnpm-lock.yaml")
    assert not evidence_candidate("templates/assets/mermaid.min.js")
    assert not evidence_candidate("src/dictation/whisper_data/tokens.json")
    assert not evidence_candidate("ui/node_modules/x/index.js")


def test_synonym_terms_exclude_retreads_and_junk():
    # intent: re-searching the ORIGINAL keywords proves nothing (they already came up dry) and
    # junk terms (non-strings, 2-char noise) waste greps — escalation must only search NEW vocabulary.
    terms = clean_synonym_terms(["ensure_peekaboo", "Dependency", "ok", None, "brew install",
                                 "ensure_peekaboo", "FilenameCompleter"],
                                kws=["optional", "dependency"])
    assert terms == ["ensure_peekaboo", "brew install", "FilenameCompleter"]


def test_escalation_flip_keeps_audit_trail():
    # intent: a gap flipped to covered by synonym evidence must keep its history (escalated flag +
    # original reasoning) — silently rewriting verdicts would make the gate's decisions unauditable.
    cats = [{"category": "optional dependency handling", "tier": "required", "status": "gap",
             "reasoning": "no matches", "fix_sites": [], "fix_sites_unverified": False}]
    out = merge_escalation(cats, {0: {"status": "covered", "reasoning": "ensure_peekaboo auto-installs",
                                      "cited_files": ["src/mod.rs"]}}, {"src/mod.rs"})
    c = out[0]
    assert c["status"] == "covered" and c["escalated"] is True
    assert c["pre_escalation_reasoning"] == "no matches"
    assert "fix_sites" not in c  # covered categories don't carry fix anchors


def test_escalation_cannot_worsen_or_invent_status():
    # intent: the re-judge is only allowed to LIFT a gap (or mark it na) — a malformed or
    # adversarial second answer must never corrupt a verdict into an unknown status.
    cats = [{"category": "A", "tier": "required", "status": "gap", "reasoning": "r"}]
    out = merge_escalation(cats, {0: {"status": "totally-bogus", "reasoning": "x"}}, set())
    assert out[0]["status"] == "gap" and out[0]["escalated"] is True
    assert "pre_escalation_reasoning" not in out[0]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
