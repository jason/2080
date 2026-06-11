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
                  "issue-surface"}    # ISSUES +0.41 ±0.06 on scope-layer work (2026-06-11)


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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
