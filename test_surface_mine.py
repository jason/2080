#!/usr/bin/env python3
"""
test_surface_mine.py — deterministic tests for the operability lens (pure layer).

No git, no subprocess: detect() and aggregate() on synthetic file lists.
Run: python3 test_surface_mine.py
"""
from surface_mine import detect, aggregate, PROBES


def test_detect_finds_artifacts_by_path_shape():
    # intent: the whole lens is path-pattern evidence; a probe matching the wrong shape
    # (e.g. 'Dockerfile.md' in docs) reports operability a neighbor doesn't have.
    files = ["Dockerfile", "deploy/docker-compose.yml", ".github/workflows/ci.yaml",
             ".github/workflows/release.yml", ".env.example", "migrations/0001_init.sql",
             "package.json", "Makefile", "CHANGELOG.md", "scripts/install.sh", "src/main.ts"]
    found = detect(files, health_hit="src/server.ts")
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
