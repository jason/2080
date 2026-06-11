#!/usr/bin/env python3
"""
test_threat_mine.py — deterministic tests for the SECURITY lens (no live network).

The OSV HTTP seam (_post_json/_get_json/urlopen) is stubbed in-process; manifest tests run
against real throwaway git repos so the git plumbing is exercised too.
Run: python3 test_threat_mine.py  (or: uv run --with pytest pytest test_threat_mine.py -q)
"""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import threat_mine
from threat_mine import (CLASSES, MAX_DEPS_PER_NEIGHBOR, UNCATEGORIZED, _parse_cargo,
                         _parse_gomod, _parse_package_json, _parse_pyproject,
                         _parse_requirements, aggregate, classify, parse_manifests, query_osv)


# ── helpers (no pytest fixtures: sibling tests stay stdlib-runnable) ─────────

@contextlib.contextmanager
def _patched(obj, name, value):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


def _mk_repo(base, files, name):
    repo = Path(base) / name
    repo.mkdir()
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    for cmd in (["init", "-q", "-b", "main"], ["add", "-A"],
                ["-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false",
                 "commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, capture_output=True)
    return str(repo)


def _run_main(argv):
    """Run threat_mine.main() in-process -> (exit_code, stdout, stderr)."""
    out, err, code = io.StringIO(), io.StringIO(), None
    with _patched(sys, "argv", ["threat_mine.py", *argv]):
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                threat_mine.main()
            except SystemExit as e:
                code = e.code
    return code, out.getvalue(), err.getvalue()


# ── manifest parsing ─────────────────────────────────────────────────────────

def test_parse_package_json_collects_deps_and_devdeps():
    # intent: devDependencies are still installed on every contributor/CI machine; dropping
    # them silently halves the npm attack surface the lens claims to measure.
    text = json.dumps({"dependencies": {"express": "^4.18.0"},
                       "devDependencies": {"lodash": "4.17.0"},
                       "scripts": {"test": "jest"}})
    assert _parse_package_json(text) == [("npm", "express"), ("npm", "lodash")]


def test_parse_requirements_strips_specifiers_and_skips_noise():
    # intent: OSV matches exact package names — "requests==2.19.0" sent verbatim matches
    # nothing, so every pinned Python stack would report zero vulns and the lens lies green.
    text = ("requests==2.19.0\n"
            "flask[async]>=2.0 ; python_version > '3.8'\n"
            "# a comment\n"
            "-r other.txt\n"
            "--hash=sha256:deadbeef\n"
            "git+https://github.com/x/y.git\n"
            "https://example.com/pkg.whl\n"
            "\n"
            "Django >= 4.2  # inline comment\n")
    assert _parse_requirements(text) == [("PyPI", "requests"), ("PyPI", "flask"),
                                         ("PyPI", "Django")]


def test_parse_pyproject_pep621_dependencies():
    # intent: PEP 621 entries carry specifiers/extras/markers inline; unstripped names make
    # every modern pyproject-only neighbor invisible to OSV.
    text = ('[project]\nname = "x"\n'
            'dependencies = ["httpx>=0.27", "pydantic[email]==2.7.0", "rich"]\n')
    assert _parse_pyproject(text) == [("PyPI", "httpx"), ("PyPI", "pydantic"), ("PyPI", "rich")]


def test_parse_cargo_dependencies_table():
    # intent: Cargo deps are TOML keys with table or string values; reading values instead of
    # keys (or choking on `{ version = ... }`) drops the whole crates.io ecosystem.
    text = ('[package]\nname = "x"\n[dependencies]\nserde = "1.0"\n'
            'tokio = { version = "1", features = ["full"] }\n')
    assert _parse_cargo(text) == [("crates.io", "serde"), ("crates.io", "tokio")]


def test_parse_gomod_block_and_single_require():
    # intent: nearly all real go.mod files use the require ( ... ) block form; parsing only
    # single-line `require X v1` would silently drop the Go ecosystem from the lens.
    text = ("module example.com/m\n\ngo 1.22\n\n"
            "require (\n"
            "\tgithub.com/gin-gonic/gin v1.9.1 // indirect\n"
            "\tgolang.org/x/crypto v0.17.0\n"
            ")\n\n"
            "require github.com/stretchr/testify v1.8.0\n")
    assert _parse_gomod(text) == [("Go", "github.com/gin-gonic/gin"),
                                  ("Go", "golang.org/x/crypto"),
                                  ("Go", "github.com/stretchr/testify")]


def test_malformed_manifest_logged_and_skipped_not_fatal():
    # intent: one neighbor shipping a broken package.json (it happens — template repos,
    # jsonc) must not kill the whole category mine; the lens loses one file, not the run.
    with tempfile.TemporaryDirectory() as tmp:
        repo = _mk_repo(tmp, {"package.json": "{ not json at all",
                              "requirements.txt": "requests==2.19.0\n"}, "nbr")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            deps = parse_manifests(repo)
        assert deps == [("PyPI", "requests")]
        assert "skip malformed manifest" in err.getvalue()
        assert "package.json" in err.getvalue()


def test_dep_cap_at_200_per_neighbor():
    # intent: a monorepo neighbor with thousands of deps would otherwise flood OSV (rate
    # limits, minutes of detail fetches) — the cap is the lens's cost/wall-time bound.
    body = "".join(f"pkg{i:04d}==1.0\n" for i in range(250))
    with tempfile.TemporaryDirectory() as tmp:
        repo = _mk_repo(tmp, {"requirements.txt": body}, "nbr")
        deps = parse_manifests(repo)
    assert len(deps) == MAX_DEPS_PER_NEIGHBOR == 200


# ── classification ───────────────────────────────────────────────────────────

def test_classify_first_match_wins_redos_before_generic_dos():
    # intent: ReDoS advisories almost always also say "denial of service"; if table order
    # isn't honored, every ReDoS lands in the generic DoS bucket and the class vanishes.
    text = ("Inefficient regular expression complexity leads to catastrophic backtracking "
            "and denial of service when matching crafted input.")
    assert classify(text) == "ReDoS defenses"
    assert classify("A denial of service via uncontrolled resource consumption.") \
        == "DoS/resource-exhaustion defenses"


def test_classify_uncategorized_fallthrough_and_never_emitted():
    # intent: vague advisories must fall through to a counted-but-unemitted bucket — an
    # "uncategorized" category in the spine would be an unjudgeable gate downstream.
    assert classify("A bug was fixed in the frobnicator module.") == UNCATEGORIZED
    assert classify("") == UNCATEGORIZED
    assert classify(None) == UNCATEGORIZED
    assert UNCATEGORIZED not in {c[0] for c in CLASSES}  # aggregate() iterates CLASSES only
    per = {"a": {UNCATEGORIZED: "x: V-1"}, "b": {UNCATEGORIZED: "y: V-2"}}
    assert aggregate(per) == []


# ── aggregation / tiering ────────────────────────────────────────────────────

def test_aggregate_convergence_tiers_and_example_shape():
    # intent: the ≥2-neighbor rule IS the mining claim ("this category's stack is empirically
    # exposed"); a required tier from one neighbor asserts convergence that doesn't exist.
    per = {"a": {"injection defenses": "sqlib: GHSA-1111"},
           "b": {"injection defenses": "qbuilder: GHSA-2222",
                 "XSS defenses": "renderer: GHSA-3333"},
           "c": {}}
    cats = {c["category"]: c for c in aggregate(per)}
    inj = cats["injection defenses"]
    assert inj["tier"] == "required"
    assert inj["projects"] == ["a", "b"]
    assert inj["recurrence_projects"] == 2
    assert inj["example"] == "sqlib: GHSA-1111"  # "pkg: VULN-ID" shape, first project's hit
    assert cats["XSS defenses"]["tier"] == "optional"
    assert "SSRF defenses" not in cats  # hit nowhere -> absent from the spine entirely
    for c in cats.values():  # assessment-contract fields downstream tools grep/gate on
        assert c["what"] and c["aliases"] and c["day1_tell"]


# ── OSV seam: chunking + retries ─────────────────────────────────────────────

def test_querybatch_chunks_of_100():
    # intent: OSV rejects oversized batches, so an unchunked POST 400s the moment a category's
    # union stack passes 100 deps — i.e. on every real multi-neighbor run.
    deps = [("PyPI", f"pkg{i:03d}") for i in range(250)]
    seen = []

    def fake_post(url, payload):
        assert url.endswith("/querybatch")
        seen.append(len(payload["queries"]))
        results = [{"vulns": [{"id": "OSV-1"}]} if q["package"]["name"] == "pkg000" else {}
                   for q in payload["queries"]]
        return {"results": results}

    with _patched(threat_mine, "_post_json", fake_post):
        out = query_osv(deps)
    assert seen == [100, 100, 50]
    assert out == {("PyPI", "pkg000"): ["OSV-1"]}


class _FakeResp:
    def __init__(self, body):
        self.body = body

    def read(self, n=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _NoSleep:
    @staticmethod
    def sleep(_s):
        pass


def test_http_retries_on_5xx_then_succeeds():
    # intent: OSV throws transient 503s under load; without retries one blip aborts a whole
    # multi-minute mine and the agent sees a spurious exit-1.
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.HTTPError("u", 503, "boom", {}, None)
        return _FakeResp(b'{"ok": 1}')

    with _patched(urllib.request, "urlopen", fake_urlopen), \
         _patched(threat_mine, "time", _NoSleep):
        assert threat_mine._http_json("https://x/y") == {"ok": 1}
    assert calls["n"] == 3  # HTTP_RETRIES=2 -> at most 3 attempts


def test_http_no_retry_on_4xx():
    # intent: retrying a permanent 4xx triple-hammers OSV and stretches every hard failure by
    # the full backoff schedule for zero benefit.
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        raise urllib.error.HTTPError("u", 404, "nope", {}, None)

    with _patched(urllib.request, "urlopen", fake_urlopen), \
         _patched(threat_mine, "time", _NoSleep):
        try:
            threat_mine._http_json("https://x/y")
            raise AssertionError("expected HTTPError")
        except urllib.error.HTTPError:
            pass
    assert calls["n"] == 1


# ── end-to-end spine + agentic contract ──────────────────────────────────────

def test_main_emits_spine_with_security_axis():
    # intent: check.py gates spines with NO axis in full (user-authored rule sets); if this
    # lens dropped the axis field, an unvalidated lens would gate without ever passing the
    # generic-baseline control.
    def fake_post(url, payload):
        results = [{"vulns": [{"id": "GHSA-AAAA"}]} if q["package"]["name"] == "leftpad" else {}
                   for q in payload["queries"]]
        return {"results": results}

    def fake_get(url):
        assert url.endswith("GHSA-AAAA")
        return {"summary": "SQL injection in leftpad",
                "details": "Crafted input reaches the query builder.",
                "severity": [{"type": "CVSS_V3", "score": "9.8"}]}

    with tempfile.TemporaryDirectory() as tmp:
        r1 = _mk_repo(tmp, {"requirements.txt": "leftpad==1.0\n"}, "nbrA")
        r2 = _mk_repo(tmp, {"requirements.txt": "leftpad==1.0\nrarelib==0.1\n"}, "nbrB")
        emit = str(Path(tmp) / "spine.json")
        with _patched(threat_mine, "_post_json", fake_post), \
             _patched(threat_mine, "_get_json", fake_get):
            code, out, err = _run_main([r1, r2, "--app-type", "test-app",
                                        "--emit", emit, "--json"])
        assert code == 0
        spine = json.loads(Path(emit).read_text())
    assert spine["axis"] == "SECURITY"
    assert spine["lens"] == "threat-surface"
    assert spine["app_type"] == "test-app"
    assert spine["derived_from"] == ["nbrA", "nbrB"]
    assert spine["stats"] == {"deps_queried": 2, "vulns_found": 1, "vulns_classified": 1}
    assert json.loads(out) == spine  # --json stdout is the same parseable document
    req = spine["required"]
    assert len(req) == 1 and spine["optional"] == []
    assert req[0]["category"] == "injection defenses"
    assert req[0]["tier"] == "required" and req[0]["projects"] == ["nbrA", "nbrB"]
    assert req[0]["example"] == "leftpad: GHSA-AAAA"


def test_security_axis_is_not_in_checks_validated_set():
    # intent: the lens must obey the advisory-until-validated discipline — SECURITY gating by
    # default would skip the very control it hasn't beaten yet.
    from check import VALIDATED_GATING_AXES
    assert "SECURITY" not in VALIDATED_GATING_AXES


def test_bare_json_is_capability_map_and_bare_run_is_usage_error():
    # intent: agents introspect via bare --json and branch on exit codes; losing either
    # blanks the agentic surface without any test going red elsewhere.
    code, out, _ = _run_main(["--json"])
    cap = json.loads(out)
    assert code == 0
    assert cap["tool"] == "threat_mine" and cap["axis"] == "SECURITY"
    assert set(cap["exit_codes"]) == {"0", "1", "2", "3"}
    code, _, err = _run_main([])
    assert code == 1 and err.strip()


def test_exit_codes_not_found_and_empty():
    # intent: 2 (bad repo path) vs 3 (no deps) are different agent branches — recoverable
    # typo vs genuinely empty category; collapsing them breaks unattended pipelines.
    with tempfile.TemporaryDirectory() as tmp:
        code, _, err = _run_main([str(Path(tmp) / "nope")])
        assert code == 2 and "not a readable git repo" in err
        repo = _mk_repo(tmp, {"README.md": "hi\n"}, "bare")
        code, _, err = _run_main([repo])
        assert code == 3 and "no dependencies" in err


def test_network_failure_exits_1_with_structured_error():
    # intent: an OSV outage must surface as exit-1 with machine-readable stderr, not a
    # traceback — agents retry on this signal instead of mis-filing it as a crash.
    def dead_post(url, payload):
        raise urllib.error.URLError("connection refused")

    with tempfile.TemporaryDirectory() as tmp:
        repo = _mk_repo(tmp, {"requirements.txt": "requests==2.19.0\n"}, "nbr")
        with _patched(threat_mine, "_post_json", dead_post):
            code, _, err = _run_main([repo, "--json"])
    assert code == 1
    payload = json.loads(err.strip().splitlines()[-1])
    assert payload["ok"] is False and payload["exit_code"] == 1
    assert "OSV API failure" in payload["error"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
