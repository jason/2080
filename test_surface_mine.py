#!/usr/bin/env python3
"""
test_surface_mine.py — deterministic tests for the operability lens (pure layer).

No git, no subprocess: detect() and aggregate() on synthetic file lists.
Run: python3 test_surface_mine.py
"""
from surface_mine import detect, aggregate, filter_content_hit, PROBES


def test_detect_finds_artifacts_by_path_shape():
    # intent: the whole lens is path-pattern evidence; a probe matching the wrong shape
    # (e.g. 'Dockerfile.md' in docs) reports operability a neighbor doesn't have.
    files = ["Dockerfile", "deploy/docker-compose.yml", ".github/workflows/ci.yaml",
             ".github/workflows/release.yml", ".env.example", "migrations/0001_init.sql",
             "package.json", "Makefile", "CHANGELOG.md", "scripts/install.sh", "src/main.ts",
             "Formula/mytool.rb", "UPGRADING.md", "completions/mytool.bash"]
    found = detect(files, health_hit="src/server.ts",
                   content_hits={"changelog discipline": "CHANGELOG.md",
                                 "telemetry/observability instrumentation": "src/metrics.ts"})
    assert set(found) == {p[0] for p in PROBES}  # every probe fires on this maximal repo
    assert found["containerization"] == "Dockerfile"
    assert found["healthcheck endpoint"] == "src/server.ts"


def test_detect_minimal_repo_fires_little():
    # intent: an empty/minimal repo must not produce phantom operability — false positives here
    # become fake convergence and a required tier nothing actually supports.
    found = detect(["src/main.py", "README.md", "docs/Dockerfile-notes.md"], health_hit=None)
    assert "containerization" not in found  # Dockerfile-notes.md is docs, not a Dockerfile
    assert "healthcheck endpoint" not in found
    assert found == {} or set(found) <= {"packaging metadata"}


def test_aggregate_convergence_tiers_and_examples():
    # intent: the ≥2-neighbor convergence rule IS the mining claim ("mature neighbors converge
    # on this"); a tier computed from one neighbor would assert convergence that doesn't exist.
    per = {"a": {"containerization": "Dockerfile", "CI pipeline": ".github/workflows/ci.yml"},
           "b": {"containerization": "docker/Dockerfile"},
           "c": {}}
    cats = {c["category"]: c for c in aggregate(per)}
    assert cats["containerization"]["tier"] == "required"
    assert cats["containerization"]["projects"] == ["a", "b"]
    assert cats["containerization"]["example"] == "Dockerfile"
    assert cats["CI pipeline"]["tier"] == "optional"
    assert "task runner" not in cats  # detected nowhere -> not in the spine at all


def test_every_probe_carries_assessment_contract_fields():
    # intent: diff_target's evidence layer greps category+aliases and gates need day1_tell;
    # a probe missing either produces an unjudgeable category three tools downstream.
    per = {"a": {p[0]: "x" for p in PROBES}, "b": {p[0]: "y" for p in PROBES}}
    for c in aggregate(per):
        assert c["aliases"] and c["day1_tell"] and c["what"]
        assert c["tier"] == "required"


def test_existing_probe_categories_unchanged():
    # intent: downstream checklists and diff_target evidence-greps key on category strings;
    # renaming or reordering an existing probe silently orphans every emitted spine entry.
    legacy = ["containerization", "compose/orchestration", "CI pipeline", "release automation",
              "config example", "schema/data migrations", "healthcheck endpoint",
              "packaging metadata", "task runner", "changelog/versioning", "install script"]
    assert [p[0] for p in PROBES[:11]] == legacy


def test_detect_distribution_channels_via_os_package_paths():
    # intent: pip/npm installability (packaging metadata) is not the same user promise as
    # brew/apt/winget; conflating them scores OS distribution a neighbor never shipped.
    found = detect(["Formula/mytool.rb", "src/main.go"])
    assert found.get("distribution channels") == "Formula/mytool.rb"
    assert "packaging metadata" not in found  # a Homebrew formula is not a language manifest
    for f in ["debian/control", "snapcraft.yaml", "PKGBUILD", "choco/mytool.nuspec",
              ".goreleaser.yaml", "manifests/m/mytool/1.0/mytool.installer.yaml",
              "flathub.json", "HomebrewFormula/mytool.rb"]:
        assert "distribution channels" in detect([f]), f
    assert "distribution channels" not in detect(["pyproject.toml", "package.json"])


def test_changelog_discipline_requires_content_hit_not_presence():
    # intent: a changelog that's just a git-log dump must not score changelog discipline —
    # presence ≠ contract; the structured-format claim rides entirely on the content grep.
    files = ["CHANGELOG.md", "src/main.py"]
    bare = detect(files)
    assert "changelog/versioning" in bare       # presence probe still fires
    assert "changelog discipline" not in bare   # no content hit -> no discipline claim
    disciplined = detect(files, content_hits={"changelog discipline": "CHANGELOG.md"})
    assert disciplined["changelog discipline"] == "CHANGELOG.md"


def test_changelog_discipline_regex_matches_contract_not_git_log():
    # intent: the content regex IS the "structured, dated, sectioned" claim; if it matches a
    # raw git-log dump (or misses Keep-a-Changelog headings) the category measures nothing.
    import re
    rx = re.compile({p[0]: p[3] for p in PROBES}["changelog discipline"])
    for line in ["## [1.2.0] - 2026-01-15", "## 0.3.1 - 2024-11-02",
                 "## [Unreleased]", "### Fixed", "### Security"]:
        assert rx.search(line), line
    for line in ["* a3f9c2 fix: handle empty input (2026-05-01)",
                 "commit a3f9c2d by jason", "merged PR #42", "## What's new"]:
        assert not rx.search(line), line


def test_migration_guides_fire_on_path_or_content():
    # intent: breaking-change support has two evidence routes (UPGRADING.md-style docs OR
    # deprecation-lifecycle text in docs); dropping either under-reports a real neighbor practice.
    assert "migration/upgrade guides" in detect(["UPGRADING.md"])
    assert "migration/upgrade guides" in detect(["docs/upgrading-to-v2.md"])
    assert "migration/upgrade guides" in detect(["docs/guides/migration.md"])
    by_content = detect(["docs/deprecations.md"],
                        content_hits={"migration/upgrade guides": "docs/deprecations.md"})
    assert by_content["migration/upgrade guides"] == "docs/deprecations.md"
    assert "migration/upgrade guides" not in detect(["docs/intro.md", "README.md"])


def test_content_hygiene_rejects_code_lockfiles_and_misplaced_docs():
    # intent: live run on AstrBot (2026-06-11) showed three precision lies the raw grep tells —
    # @deprecated in src code claimed "upgrade guides", an opentelemetry line in uv.lock claimed
    # instrumentation, and `### Added` in a random docs page claimed changelog discipline. The
    # hygiene filter is what keeps content evidence meaning what the category claims.
    assert filter_content_hit("migration/upgrade guides",
                              ["astrbot/core/agent/tool.py", "docs/upgrade-notes.md"]) == \
        "docs/upgrade-notes.md"
    assert filter_content_hit("migration/upgrade guides", ["src/api.py"]) is None
    assert filter_content_hit("telemetry/observability instrumentation",
                              ["uv.lock", "package-lock.json", "go.sum"]) is None
    assert filter_content_hit("telemetry/observability instrumentation",
                              ["uv.lock", "src/obs.py"]) == "src/obs.py"
    assert filter_content_hit("changelog discipline",
                              ["docs/en/use/webui.md", "CHANGELOG.md"]) == "CHANGELOG.md"
    assert filter_content_hit("changelog discipline", ["changelogs/v3.4.1.md"]) == \
        "changelogs/v3.4.1.md"
    assert filter_content_hit("changelog discipline", ["docs/usage.md"]) is None
    # intent: bundled runtimes (shiki_runtime.iife.js, *.min.js, vendor/) carry other projects'
    # vocabulary — the live AstrBot run scored CLI polish off a syntax-highlighter bundle.
    assert filter_content_hit("CLI polish (completions/man pages)",
                              ["core/utils/t2i/template/shiki_runtime.iife.js"]) is None
    assert filter_content_hit("CLI polish (completions/man pages)",
                              ["vendor/lib.js", "src/cli.rs"]) == "src/cli.rs"


def test_telemetry_is_content_only_no_path_phantoms():
    # intent: observability can't be inferred from any path shape; a dir named metrics/ with
    # dashboards in it would claim instrumentation that's actually just print statements.
    assert "telemetry/observability instrumentation" not in detect(
        ["metrics/dashboard.png", "src/main.py"])
    hit = detect(["src/main.py"],
                 content_hits={"telemetry/observability instrumentation": "src/obs.py"})
    assert hit["telemetry/observability instrumentation"] == "src/obs.py"


def test_cli_polish_path_and_content_fallback():
    # intent: completions shipped as files OR generated by code (clap_complete/shtab) are the
    # same user-facing polish; detecting only one route splits the category arbitrarily.
    found = detect(["completions/mytool.bash"])
    assert found["CLI polish (completions/man pages)"] == "completions/mytool.bash"
    assert "CLI polish (completions/man pages)" in detect(["man/mytool.1"])
    assert "CLI polish (completions/man pages)" in detect(["docs/mytool.1.md"])
    gen = detect(["src/cli.rs"],
                 content_hits={"CLI polish (completions/man pages)": "src/cli.rs"})
    assert gen["CLI polish (completions/man pages)"] == "src/cli.rs"
    assert "CLI polish (completions/man pages)" not in detect(["src/main.rs", "README.md"])
    # intent: version-numbered release notes (changelogs/v3.4.1.md) masquerade as `.1.md` man
    # pages — the live AstrBot run scored CLI polish off a changelog entry.
    assert "CLI polish (completions/man pages)" not in detect(["changelogs/v3.4.1.md"])
    assert "CLI polish (completions/man pages)" not in detect(["docs/v2.1.md"])


def test_operability_axis_is_not_in_checks_validated_set():
    # intent: the deterministic lens must obey the same advisory-until-validated discipline as
    # the LLM lenses — OPERABILITY gating by default would skip the control it hasn't passed.
    from check import VALIDATED_GATING_AXES
    assert "OPERABILITY" not in VALIDATED_GATING_AXES


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
