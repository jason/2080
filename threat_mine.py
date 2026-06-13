#!/usr/bin/env python3
"""
threat_mine.py — the SECURITY lens, deterministic mining over OSV (no LLM, no cost).

Which vulnerability classes hit the dependency stacks this category of app converges on?
Parse each mature neighbor's manifests (package.json / requirements*.txt / pyproject.toml /
Cargo.toml / go.mod) for direct dependencies, query OSV (https://osv.dev) for known vulns in
those packages, classify each vuln's text through an ordered keyword table, and emit a
checklist-compatible spine: one category per vulnerability class the category's stack is
empirically exposed to. Convergence tiering matches the other mines: ≥2 neighbors affected →
required, 1 → optional. Axis SECURITY — ADVISORY in check.py (like every non-validated axis)
until this lens beats the generic-baseline control.

OSV text is untrusted data: it flows only into deterministic keyword matching (bounded read,
truncated before regex), never into prompts or shell commands.

SCAN MODE (--scan): the same plumbing pointed at the TARGET instead of neighbors — a direct
supply-chain check that reports every direct dependency with known OSV advisories as a
finding. Findings exit 3 (mirrors check.py's GATED), clean exits 0.

Usage: threat_mine.py <neighbor-repo-dir>... [--app-type T] [--max-vulns N] [--emit PATH] [--json]
       threat_mine.py --scan <target-repo>... [--json]
Exit codes: 0 OK/clean | 1 USAGE/ERR (incl. network failure after retries) | 2 NOT_FOUND
            | 3 mine: EMPTY / scan: findings
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys, time, tomllib
import urllib.error, urllib.parse, urllib.request
from pathlib import Path

from mine_common import write_atomic, git_text as _git, EXIT_OK, EXIT_ERR, EXIT_NOT_FOUND, EXIT_EMPTY
from lens_mine import neighbor_name

OSV_API = "https://api.osv.dev/v1"
MAX_DEPS_PER_NEIGHBOR = 200
QUERYBATCH_CHUNK = 100
MAX_RESPONSE_BYTES = 8 * 1024 * 1024   # cap reads — OSV text is untrusted
MAX_CLASSIFY_CHARS = 20000             # bound the regex pass per vuln
HTTP_TIMEOUT_S = 30
HTTP_RETRIES = 2
UNCATEGORIZED = "uncategorized"

_AUDIT = ("Run a dependency audit (osv-scanner / npm audit / pip-audit) in CI and confirm it "
          "fails the build on a known-vulnerable pin; ")

# Ordered keyword table — FIRST MATCH WINS (e.g. ReDoS before generic DoS, because ReDoS
# advisories almost always also say "denial of service"). Matched against lowercased text.
# (category, what, keyword regex, aliases, day1_tell)
CLASSES = [
    ("injection defenses",
     "Injection vulnerabilities (SQL/command/code/template) have empirically hit this category's dependency stack.",
     r"sql injection|command injection|code injection|template injection",
     "sql injection / command injection / code injection / template injection",
     _AUDIT + "fuzz every input that reaches a query, shell, or template sink."),
    ("XSS defenses",
     "Cross-site scripting vulnerabilities have empirically hit this category's dependency stack.",
     r"cross-site scripting|\bxss\b",
     "cross-site scripting / xss / script injection / output escaping",
     _AUDIT + "render hostile markup through every user-content path and confirm it is escaped."),
    ("path traversal defenses",
     "Path traversal / arbitrary-file vulnerabilities have empirically hit this category's dependency stack.",
     r"traversal|zip slip|arbitrary file",
     "path traversal / directory traversal / zip slip / arbitrary file read or write",
     _AUDIT + "request `../`-style paths through every file-serving route and confirm they are rejected."),
    ("SSRF defenses",
     "Server-side request forgery vulnerabilities have empirically hit this category's dependency stack.",
     r"server-side request forgery|\bssrf\b",
     "ssrf / server-side request forgery / internal address fetch",
     _AUDIT + "point every URL-fetching feature at an internal address (localhost, 169.254.169.254) and confirm it is blocked."),
    ("deserialization defenses",
     "Unsafe-deserialization vulnerabilities (pickle/prototype pollution) have empirically hit this category's dependency stack.",
     r"deserializ|pickle|prototype pollution",
     "unsafe deserialization / pickle / prototype pollution / object injection",
     _AUDIT + "feed crafted payloads to every deserialization entry point and confirm unsafe loaders are absent."),
    ("ReDoS defenses",
     "Regular-expression denial-of-service vulnerabilities have empirically hit this category's dependency stack.",
     r"\bredos\b|catastrophic backtracking|inefficient regular expression",
     "redos / catastrophic backtracking / inefficient regular expression",
     _AUDIT + "run pathological inputs against user-facing regexes and confirm matching is time-bounded."),
    ("DoS/resource-exhaustion defenses",
     "Denial-of-service / resource-exhaustion vulnerabilities have empirically hit this category's dependency stack.",
     r"denial.of.service|resource exhaustion|uncontrolled resource",
     "denial of service / resource exhaustion / memory exhaustion / flood",
     _AUDIT + "replay oversized and flood inputs against the busiest endpoint and confirm size, rate, and timeout limits hold."),
    ("secrets/credential-exposure defenses",
     "Credential/secret-exposure vulnerabilities have empirically hit this category's dependency stack.",
     r"credential|\bsecrets?\b|sensitive information|information disclosure|information exposure",
     "credential exposure / secret leak / sensitive information disclosure",
     _AUDIT + "force a failure path and grep logs and error responses to confirm no tokens or credentials leak."),
    ("auth/authz bypass defenses",
     "Authentication/authorization-bypass vulnerabilities have empirically hit this category's dependency stack.",
     r"authentication bypass|authorization bypass|auth bypass|access control|privilege escalation",
     "authentication bypass / authorization bypass / access control / privilege escalation",
     _AUDIT + "replay a privileged request with no session and a downgraded session and confirm both are denied."),
    ("supply-chain defenses",
     "Supply-chain attacks (malicious/typosquatted packages) have empirically hit this category's dependency stack.",
     r"malicious package|typosquat|dependency confusion",
     "malicious package / typosquatting / dependency confusion / lockfile pinning",
     _AUDIT + "verify lockfile pinning and provenance (hashes, registry provenance) for every direct dependency."),
    ("memory-safety defenses",
     "Memory-safety vulnerabilities (overflow/UAF/OOB) have empirically hit this category's dependency stack.",
     r"buffer overflow|use.after.free|out.of.bounds",
     "buffer overflow / use after free / out-of-bounds read or write",
     _AUDIT + "run the native-code surface under a fuzzer with sanitizers and confirm no crashes on malformed input."),
    ("crypto-weakness defenses",
     "Cryptographic-weakness vulnerabilities have empirically hit this category's dependency stack.",
     r"cryptograph|weak cipher|insecure random|timing attack",
     "weak cryptography / weak cipher / insecure randomness / timing attack",
     _AUDIT + "inventory cipher, hash, and randomness usage and confirm no deprecated primitives remain."),
]


# ── manifest parsing (pure text -> [(ecosystem, name)]) ──────────────────────

_REQ_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")


def _parse_package_json(text):
    data = json.loads(text)
    out = []
    for key in ("dependencies", "devDependencies"):
        sec = data.get(key)
        if isinstance(sec, dict):
            out.extend(("npm", str(n)) for n in sec)
    return out


def _parse_requirements(text):
    out = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].split(";", 1)[0].strip()
        if not line or line.startswith("-") or "://" in line or line.startswith(("git+", "hg+", "svn+")):
            continue  # options (-r/-e/--hash), URL/VCS requirements: not OSV package names
        m = _REQ_NAME_RE.match(line)
        if m:
            out.append(("PyPI", m.group(0)))
    return out


def _parse_pyproject(text):
    deps = tomllib.loads(text).get("project", {}).get("dependencies", [])
    out = []
    for d in deps if isinstance(deps, list) else []:
        m = _REQ_NAME_RE.match(str(d).strip())
        if m:
            out.append(("PyPI", m.group(0)))
    return out


def _parse_cargo(text):
    deps = tomllib.loads(text).get("dependencies")
    return [("crates.io", str(n)) for n in deps] if isinstance(deps, dict) else []


def _parse_gomod(text):
    out, in_block = [], False
    for raw in text.splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line:
            continue
        if line.startswith("require ("):
            in_block = True
        elif in_block and line == ")":
            in_block = False
        elif in_block:
            out.append(("Go", line.split()[0]))
        elif line.startswith("require "):
            parts = line.split()
            if len(parts) >= 2:
                out.append(("Go", parts[1]))
    return out


MANIFESTS = [
    (re.compile(r"(^|/)package\.json$"), _parse_package_json),
    (re.compile(r"(^|/)requirements[^/]*\.txt$"), _parse_requirements),
    (re.compile(r"(^|/)pyproject\.toml$"), _parse_pyproject),
    (re.compile(r"(^|/)Cargo\.toml$"), _parse_cargo),
    (re.compile(r"(^|/)go\.mod$"), _parse_gomod),
]


def parse_manifests(repo_dir):
    """Direct deps from a neighbor's tracked manifests -> [(ecosystem, name)], unique, capped.
    A malformed manifest is logged and skipped — one broken file must not kill the lens."""
    files = _git(repo_dir, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
    deps, seen = [], set()
    for f in files:
        parser = next((p for rx, p in MANIFESTS if rx.search(f)), None)
        if parser is None:
            continue
        try:
            parsed = parser(_git(repo_dir, "show", f"HEAD:{f}"))
        except Exception as e:
            print(f"skip malformed manifest {repo_dir}:{f}: {e}", file=sys.stderr)
            continue
        for pair in parsed:
            if pair not in seen:
                seen.add(pair)
                deps.append(pair)
                if len(deps) >= MAX_DEPS_PER_NEIGHBOR:
                    return deps
    return deps


# ── OSV HTTP seam (the only network surface; tests stub _post_json/_get_json) ─

def _http_json(url, payload=None):
    """One JSON request, bounded read, HTTP_RETRIES retries w/ backoff on 5xx/URLError."""
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    for attempt in range(HTTP_RETRIES + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as r:
                return json.loads(r.read(MAX_RESPONSE_BYTES))
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == HTTP_RETRIES:
                raise
        except urllib.error.URLError:
            if attempt == HTTP_RETRIES:
                raise
        time.sleep(2 ** attempt)


def _post_json(url, payload):
    return _http_json(url, payload)


def _get_json(url):
    return _http_json(url)


def query_osv(deps):
    """[(ecosystem, name)] -> {(ecosystem, name): [vuln ids, newest-id-first]} via querybatch."""
    vulns_by_pkg = {}
    for i in range(0, len(deps), QUERYBATCH_CHUNK):
        chunk = deps[i:i + QUERYBATCH_CHUNK]
        payload = {"queries": [{"package": {"name": n, "ecosystem": e}} for e, n in chunk]}
        resp = _post_json(f"{OSV_API}/querybatch", payload) or {}
        for (e, n), res in zip(chunk, resp.get("results", [])):
            ids = sorted({v.get("id") for v in (res or {}).get("vulns") or [] if v.get("id")},
                         reverse=True)
            if ids:
                vulns_by_pkg[(e, n)] = ids
    return vulns_by_pkg


def fetch_vulns(ids):
    """vuln ids -> {id: {text, severity}}. OSV text is untrusted: truncated, keyword-matched only."""
    details = {}
    for vid in ids:
        v = _get_json(f"{OSV_API}/vulns/{urllib.parse.quote(str(vid), safe='')}") or {}
        sevs = v.get("severity")
        sev = str(sevs[0].get("score", "")) if isinstance(sevs, list) and sevs and isinstance(sevs[0], dict) else ""
        text = f"{v.get('summary', '')} {v.get('details', '')}".strip()[:MAX_CLASSIFY_CHARS]
        details[vid] = {"text": text, "severity": sev}
    return details


# ── deterministic classification + aggregation (pure) ────────────────────────

def classify(text):
    """Vuln text -> vulnerability-class category. First match in CLASSES wins; else uncategorized."""
    t = (text or "").lower()
    for cat, _what, pat, _al, _tell in CLASSES:
        if re.search(pat, t):
            return cat
    return UNCATEGORIZED


def aggregate(per_neighbor):
    """{neighbor: {category: 'pkg: VULN-ID'}} -> checklist categories with convergence tiers (pure)."""
    cats = []
    for cat, what, _pat, aliases, tell in CLASSES:
        projs = sorted(n for n, found in per_neighbor.items() if cat in found)
        if not projs:
            continue
        example = next(per_neighbor[p][cat] for p in projs)
        cats.append({"category": cat, "what": what, "aliases": aliases,
                     "projects": projs, "recurrence_projects": len(projs),
                     "tier": "required" if len(projs) >= 2 else "optional",
                     "example": example if isinstance(example, str) else "",
                     "day1_tell": tell})
    return cats


def build_scan_report(target, deps, vulns_by_pkg, details):
    """TARGET-side findings: every direct dependency with known OSV vulns, newest-id-first,
    classified into this lens's threat classes (pure — tests feed synthetic OSV data)."""
    findings = []
    for eco, name in sorted(deps):
        ids = vulns_by_pkg.get((eco, name))
        if not ids:
            continue
        top = details.get(ids[0], {})
        findings.append({"ecosystem": eco, "package": name, "vulns": ids,
                         "class": classify(top.get("text", "")),
                         "severity": top.get("severity", ""),
                         "summary": top.get("text", "")[:200]})
    return {"tool": "threat_mine", "mode": "scan", "target": target,
            "deps_scanned": len(deps), "vulnerable": len(findings),
            "ok": not findings, "findings": findings}


def capability_map():
    return {"tool": "threat_mine", "version": "0.2", "lens": "threat-surface",
            "axis": "SECURITY", "deterministic": True,
            "args": "<neighbor-repo-dir>... [--app-type T] [--max-vulns N] [--emit PATH] [--json] | "
                    "--scan <target-repo> [--json]",
            "scan": "target-side supply-chain check: the TARGET's direct deps vs OSV; "
                    "findings -> exit 3 (mirrors check.py's gate), clean -> 0",
            "classes": [c[0] for c in CLASSES],
            "ecosystems": ["npm", "PyPI", "crates.io", "Go"],
            "gating": "SECURITY is advisory in check.py until this lens beats the generic-baseline control",
            "exit_codes": {"0": "ok / scan clean", "1": "usage/err (incl. network failure after retries)",
                           "2": "not_found", "3": "mine: empty (no deps or no classifiable vulns); "
                                                  "scan: known vulnerabilities found"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repos", nargs="*")
    ap.add_argument("--app-type", default="ai-agent-tool")
    ap.add_argument("--max-vulns", type=int, default=150,
                    help="cap on vuln detail fetches (newest-id-first, deterministic)")
    ap.add_argument("--emit", metavar="PATH")
    ap.add_argument("--scan", action="store_true",
                    help="scan mode: repos are TARGETS — report their own vulnerable deps "
                         "(exit 3 on findings) instead of mining a neighbor spine")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.scan and a.repos:
        worst = EXIT_OK
        for repo in a.repos:
            files = _git(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
            if not files:
                print(f"not a readable git repo: {repo}", file=sys.stderr); sys.exit(EXIT_NOT_FOUND)
            deps = parse_manifests(repo)
            try:
                vulns_by_pkg = query_osv(deps)
                first_ids = [ids[0] for ids in vulns_by_pkg.values()]
                details = fetch_vulns(sorted(set(first_ids))[:a.max_vulns])
            except (OSError, ValueError) as e:
                # aborts the WHOLE batch, discarding earlier repos' output — deliberate
                # fail-closed: a supply-chain gate that half-ran must not exit clean
                print(json.dumps({"ok": False, "error": f"OSV API failure after retries: {e}",
                                  "exit_code": EXIT_ERR}), file=sys.stderr)
                sys.exit(EXIT_ERR)
            report = build_scan_report(repo, deps, vulns_by_pkg, details)
            if a.json:
                print(json.dumps(report, indent=2))
            else:
                print(f"=== supply-chain scan: {repo} ({report['deps_scanned']} direct deps) ===")
                if not report["findings"]:
                    print("clean — no known OSV vulnerabilities in direct dependencies")
                for f in report["findings"]:
                    print(f"  ⚠ {f['package']} ({f['ecosystem']}) — {len(f['vulns'])} advisories, "
                          f"newest {f['vulns'][0]} [{f['class']}] {f['severity']}")
            if report["findings"]:
                worst = EXIT_EMPTY  # 3 — mirrors check.py's GATED: findings demand attention
        sys.exit(worst)

    if not a.repos:
        if a.json:
            print(json.dumps(capability_map())); sys.exit(EXIT_OK)
        print(capability_map()["args"], file=sys.stderr); sys.exit(EXIT_ERR)

    per_neighbor_deps = {}
    for repo in a.repos:
        files = _git(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
        if not files:
            print(f"not a readable git repo: {repo}", file=sys.stderr); sys.exit(EXIT_NOT_FOUND)
        per_neighbor_deps[neighbor_name(repo)] = parse_manifests(repo)

    all_deps = sorted({d for deps in per_neighbor_deps.values() for d in deps})
    if not all_deps:
        print("no dependencies found in any neighbor manifest", file=sys.stderr); sys.exit(EXIT_EMPTY)

    try:
        vulns_by_pkg = query_osv(all_deps)
        all_ids = sorted({i for ids in vulns_by_pkg.values() for i in ids}, reverse=True)
        details = fetch_vulns(all_ids[:a.max_vulns])
    except (OSError, ValueError) as e:
        print(json.dumps({"ok": False, "error": f"OSV API failure after retries: {e}",
                          "exit_code": EXIT_ERR}), file=sys.stderr)
        sys.exit(EXIT_ERR)

    if not vulns_by_pkg:
        print("no known vulnerabilities for any neighbor dependency", file=sys.stderr)
        sys.exit(EXIT_EMPTY)

    class_of = {vid: classify(d["text"]) for vid, d in details.items()}
    per_neighbor = {}
    for nb, deps in per_neighbor_deps.items():
        found = {}
        for eco, name in sorted(deps):
            for vid in vulns_by_pkg.get((eco, name), []):
                cat = class_of.get(vid)
                if cat and cat != UNCATEGORIZED and cat not in found:
                    found[cat] = f"{name}: {vid}"
        per_neighbor[nb] = found

    cats = aggregate(per_neighbor)
    if not cats:
        print("vulnerabilities found but none classifiable into a threat class", file=sys.stderr)
        sys.exit(EXIT_EMPTY)

    derived = sorted(per_neighbor)
    stats = {"deps_queried": len(all_deps),
             "vulns_found": len(all_ids),
             "vulns_classified": sum(1 for c in class_of.values() if c != UNCATEGORIZED)}
    required = [c for c in cats if c["tier"] == "required"]
    optional = [c for c in cats if c["tier"] == "optional"]
    checklist = {
        "app_type": a.app_type,
        "lens": "threat-surface",
        "axis": "SECURITY",
        "scope_note": (f"SECURITY-axis spine for {a.app_type}: deterministic OSV mining over "
                       f"{derived} — which vulnerability classes hit the dependency stacks this "
                       f"category converges on. Advisory in check.py until this lens beats the "
                       f"generic-baseline control."),
        "derived_from": derived,
        "stats": stats,
        "required": required,
        "optional": optional,
    }
    if a.emit:
        write_atomic(Path(a.emit), json.dumps(checklist, indent=2))
        print(f"→ {a.app_type} threat spine: {len(required)} convergent + {len(optional)} "
              f"single-neighbor ({stats['vulns_found']} vulns over {stats['deps_queried']} deps) "
              f"→ {a.emit}", file=sys.stderr)
    if a.json:
        print(json.dumps(checklist, indent=2)); sys.exit(EXIT_OK)

    print(f"=== {a.app_type} SECURITY threat spine (deterministic) ===")
    print(f"derived from: {derived}")
    print(f"stats: {stats['deps_queried']} deps queried, {stats['vulns_found']} vulns, "
          f"{stats['vulns_classified']} classified\n")
    for c in required:
        print(f"  🔁 {c['category']}  {c['projects']}  (e.g. {c['example']})")
    for c in optional:
        print(f"  ·  {c['category']}  {c['projects']}")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
