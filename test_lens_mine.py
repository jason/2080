#!/usr/bin/env python3
"""
test_lens_mine.py — deterministic tests for the lens registry + pure extraction helpers.

No LLM, no git, no gh: exercises the pure layer of the five LLM lenses.
Run: python3 test_lens_mine.py
"""
from lens_mine import (LENSES, slug_from_url, format_issue_lines, config_material,
                          synth_prompt, CONFIG_FILE_RE, TEST_PATH_RE)


def test_registry_every_lens_is_complete():
    # intent: a lens missing axis/source/abstract crashes mid-mine after the user already paid
    # for neighbor cloning — the registry contract must hold for every entry, including new ones.
    for name, lens in LENSES.items():
        for key in ("axis", "desc", "source", "material_label", "abstract", "day1_kind"):
            assert key in lens, f"{name} missing {key}"
        assert callable(lens["source"])


# Lenses that PASSED the generic-baseline control (measure.py, strict judges, ×3 each).
# Promoting a lens here without that measurement is the exact failure the tripwire prevents.
CONTROL_PASSED = {"feature-surface",  # SCOPE  +0.27 ±0.05 (2026-06)
                  "issue-surface",    # ISSUES +0.41 ±0.06 on scope-layer work (2026-06-11)
                  "test-surface"}     # TESTS  +0.61 ±0.01 scope AND +0.28 ±0.00 robustness (2026-06-11)


def test_registry_only_control_passed_lenses_may_gate():
    # intent: the codified discipline — a lens's axis may sit in check.py's validated set ONLY
    # after beating the generic-baseline control; a new lens reusing a validated axis name (or
    # a premature promotion) would silently gain gating power without the measurement.
    from check import VALIDATED_GATING_AXES
    assert "SCOPE" in VALIDATED_GATING_AXES
    for n, l in LENSES.items():
        gates = l["axis"].upper() in VALIDATED_GATING_AXES
        assert gates == (n in CONTROL_PASSED), \
            f"{n}: gating={gates} but control-passed={n in CONTROL_PASSED}"


def test_merge_baseline_floor_appends_only_uncovered_categories():
    # intent: the baseline floor is the ONLY gating part of a robustness spine (measured: generic
    # beats mined, −0.15); dropping it un-gates robustness entirely, while duplicating an
    # already-mined vocabulary doubles a category and confuses assessment. (Moved with the
    # cluster_fixes→lens_mine supersession, 2026-06-11.)
    from lens_mine import merge_baseline
    cats = [{"category": "timeout error handling", "aliases": "timeout handling / retries"}]
    baseline = [{"category": "retry and timeout handling", "aliases": "retries / timeouts / backoff"},
                {"category": "internationalization", "aliases": "i18n / localization"}]
    added = merge_baseline(cats, baseline)
    assert added == 1  # retry/timeout vocabulary already mined -> skipped; i18n appended
    assert cats[-1]["category"] == "internationalization"
    assert cats[-1]["origin"] == "generic-baseline" and cats[-1]["tier"] == "required"


def test_norm_name_matches_product_name_variants():
    # intent: the model attributes categories to PRODUCT names ('open-interpreter', 'Aider')
    # while canonical names are clone-dir names ('openinterpreter'); exact-match dropped every
    # attribution and emitted a 0-required spine (live failure 2026-06-11). Never again.
    from lens_mine import norm_name
    assert norm_name("Open-Interpreter") == norm_name("openinterpreter") == norm_name("open_interpreter")
    assert norm_name("Aider") == norm_name("aider")
    assert norm_name("gptme") != norm_name("aider")


def test_slug_from_url_handles_https_ssh_and_junk():
    # intent: the issue lens derives the gh API target from the clone's remote; a mis-parsed
    # slug fetches a stranger's issues (wrong data) or crashes the whole mine on a local remote.
    assert slug_from_url("https://github.com/owner/repo.git") == "owner/repo"
    assert slug_from_url("git@github.com:owner/repo.git") == "owner/repo"
    assert slug_from_url("https://github.com/owner/repo/") == "owner/repo"
    assert slug_from_url("/local/path/repo") is None
    assert slug_from_url("") is None


def test_issue_lines_exclude_prs_and_rank_by_reactions():
    # intent: the GitHub issues API mixes in PRs (not user-experienced gaps), and low-signal
    # one-offs must rank below high-reaction demands — the material cap keeps only the top.
    items = [{"title": "PR: refactor", "state": "open", "pull_request": {}},
             {"title": "bot crashes on long messages", "state": "closed",
              "reactions": {"total_count": 12}},
             {"title": "minor typo", "state": "open", "reactions": {"total_count": 0}},
             {"not_an_issue": True}]
    lines = format_issue_lines(items)
    assert len(lines) == 2
    assert "crashes on long messages" in lines[0] and "(+12)" in lines[0]
    assert "typo" in lines[1]


def test_config_material_surfaces_recurring_env_tokens():
    # intent: config mining is only as good as its token extraction — prose words and
    # one-letter noise must not appear, and recurring keys must rank first.
    files = ["src/app.py", ".env.example", "config.example.yaml", "docs/x.md"]
    blobs = ["API_TIMEOUT=30\nPROXY_URL=\nsome prose here", "API_TIMEOUT: 30\nRATE_LIMIT: 5"]
    m = config_material(files, blobs)
    assert ".env.example" in m and "config.example.yaml" in m and "src/app.py" not in m
    toks = m.split("config keys:\n")[1].splitlines()
    assert toks[0] == "API_TIMEOUT"  # appears in 2 blobs -> first
    assert "prose" not in m.lower().split("config keys:")[1]


def test_config_material_excludes_dev_tooling_configs():
    # intent: dev-tooling configs (tsconfig, eslint, pytest) describe how the project is BUILT,
    # not what an operator configures — mining them is why the config lens scored only +0.10 in
    # the 2026-06-11 control ("build/typecheck toolchain" came back as a required knob group).
    files = ["tsconfig.json", ".eslintrc.config.json", "pytest-config.yaml",
             ".env.example", "config/settings.example.yaml"]
    m = config_material(files, [])
    assert ".env.example" in m and "config/settings.example.yaml" in m
    assert "tsconfig" not in m and "eslint" not in m and "pytest" not in m


def test_path_regexes_classify_correctly():
    # intent: TEST_PATH_RE/CONFIG_FILE_RE feed two lenses' material; a regex matching src files
    # as tests (or lockfiles as config) poisons the spine upstream of every later stage.
    assert TEST_PATH_RE.search("tests/test_api.py") and TEST_PATH_RE.search("src/api_test.go")
    assert TEST_PATH_RE.search("src/__tests__/x.ts") and not TEST_PATH_RE.search("src/contest.py")
    assert CONFIG_FILE_RE.search(".env.example") and CONFIG_FILE_RE.search("docker-compose.prod.yml")
    assert not CONFIG_FILE_RE.search("src/main.rs")


def test_synth_prompt_uses_lens_prose_and_constrains_neighbors():
    # intent: cross-lens prompt reuse must still constrain the model to the named neighbors —
    # invented project names would fabricate convergence (the tier is COUNTED from them).
    mats = [{"name": "alpha", "block": "stuff"}, {"name": "beta", "block": "things"}]
    p = synth_prompt(mats, "telegram-llm-bot", LENSES["issue-surface"])
    assert "alpha" in p and "beta" in p and "invent no others" in p
    assert "USERS" in p  # the issue lens's own abstract prose, not feature-surface's


def test_discussions_surface_registered_and_advisory_only():
    # intent: an unvalidated demand lens must never gate the day-1 map — DISCUSSIONS stays out of
    # check.py's validated set and out of CONTROL_PASSED until it beats the generic-baseline
    # control in measure.py (the same bar SCOPE and ISSUES passed).
    from check import VALIDATED_GATING_AXES
    lens = LENSES["discussions-surface"]
    assert lens["axis"] == "DISCUSSIONS"
    assert "DISCUSSIONS" not in VALIDATED_GATING_AXES
    assert "discussions-surface" not in CONTROL_PASSED


def _run_discussions_source(fake_run, repo):
    """Patch the gh/git subprocess seam + cache dir, run the discussions source, return
    (block, stderr_text). Same attribute-patch/finally-restore style as test_mine_common."""
    import contextlib, io, os, tempfile
    import lens_mine
    real_run, real_cache = lens_mine.subprocess.run, os.environ.get("CACHE_2080")
    err = io.StringIO()
    with tempfile.TemporaryDirectory() as d:
        os.environ["CACHE_2080"] = d
        lens_mine.subprocess.run = fake_run
        try:
            with contextlib.redirect_stderr(err):
                block = lens_mine._discussions_surface_source(repo)
        finally:
            lens_mine.subprocess.run = real_run
            if real_cache is None:
                os.environ.pop("CACHE_2080", None)
            else:
                os.environ["CACHE_2080"] = real_cache
    return block, err.getvalue()


def test_discussions_source_filters_answered_and_ranks_by_weight():
    # intent: an answered discussion is a CLOSED gap — mining it reports resolved demand as a
    # missing capability; and upvote+comment weighting must rank persistent demands above
    # one-off questions so the material cap keeps the right threads.
    import json as _json
    from subprocess import CompletedProcess
    nodes = [
        {"title": "how do I deploy this", "body": "x" * 500, "upvoteCount": 2,
         "isAnswered": False, "category": {"name": "Q&A"}, "comments": {"totalCount": 1}},
        {"title": "already solved question", "body": "", "upvoteCount": 50,
         "isAnswered": True, "category": {"name": "Q&A"}, "comments": {"totalCount": 9}},
        {"title": "webhook support", "body": "please add", "upvoteCount": 7,
         "isAnswered": False, "category": {"name": "Ideas"}, "comments": {"totalCount": 5}},
        {"not_a_discussion": True},
    ]
    payload = {"data": {"repository": {"discussions": {"nodes": nodes}}}}

    def fake_run(cmd, **kw):
        if cmd[0] == "git":
            return CompletedProcess(cmd, 0, "https://github.com/owner/repo.git\n", "")
        assert cmd[:3] == ["gh", "api", "graphql"]
        return CompletedProcess(cmd, 0, _json.dumps(payload), "")

    block, _ = _run_discussions_source(fake_run, "/tmp/neighbors/repo")
    lines = block.splitlines()
    assert len(lines) == 2 and "already solved" not in block
    assert "webhook support" in lines[0] and "(+12)" in lines[0]  # 7 upvotes + 5 comments first
    assert "deploy" in lines[1] and "(+3)" in lines[1]
    assert "x" * 120 in lines[1] and "x" * 121 not in lines[1]  # body truncated like issue titles


def test_discussions_disabled_neighbor_is_skipped_not_fatal():
    # intent: one neighbor without Discussions must not kill the whole mine — a gh GraphQL error
    # degrades to a logged empty block (main() drops that neighbor; only ALL-empty exits 3).
    from subprocess import CompletedProcess

    def fake_run(cmd, **kw):
        if cmd[0] == "git":
            return CompletedProcess(cmd, 0, "https://github.com/owner/nodisc.git\n", "")
        return CompletedProcess(cmd, 1, "", "GraphQL: Discussions are disabled for this repository")

    block, err = _run_discussions_source(fake_run, "/tmp/neighbors/nodisc")
    assert block == ""
    assert "nodisc" in err and "skip" in err.lower()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
