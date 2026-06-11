#!/usr/bin/env python3
"""
surface_mine.py — the OPERABILITY lens, fully deterministic (no LLM, no cost).

What do mature neighbors ship AROUND the code: Dockerfile, compose, CI, release automation,
config example, migrations, healthcheck, packaging… This is classic second-85% material —
invisible in a demo, mandatory in production, highly convergent per app type — and it's pure
file-presence evidence, so mining it needs zero LLM calls and is exactly reproducible.

Each probe = one category. A neighbor "has" the category if any tracked path matches, or —
for probes that declare a content regex — if `git grep -lIE` over HEAD hits (path hit wins
when a probe declares both). Convergence tiering matches the other mines: ≥2 neighbors →
required, 1 → optional. Emits a checklist-compatible spine with axis OPERABILITY — ADVISORY in
check.py (like every non-SCOPE axis) until this lens beats the generic-baseline control.

Usage: surface_mine.py <neighbor-repo-dir>... [--app-type T] [--emit PATH] [--json]
Exit codes: 0 OK | 1 USAGE/ERR | 2 NOT_FOUND | 3 EMPTY
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from pathlib import Path

from mine_common import write_atomic, git_text as _git, EXIT_OK, EXIT_ERR, EXIT_NOT_FOUND, EXIT_EMPTY
from lens_mine import neighbor_name

HEALTH_RE = r"healthz|readyz|/health|health_check|healthcheck"

# (category, what, path regex, content regex, aliases-for-evidence-grep, day1_tell)
# path regex matches tracked paths; content regex (optional) is grepped via
# `git -C repo grep -lIE <re> HEAD` — same mechanism the healthcheck probe always used.
# A probe may declare either or both; when both, a path hit wins and content is fallback.
PROBES = [
    ("containerization", "Ships a container image definition.",
     r"(^|/)(Dockerfile|Containerfile)(\.[^/]+)?$", None,
     "docker / container image / dockerfile",
     "Build the container image from the repo's Dockerfile and run it."),
    ("compose/orchestration", "Ships multi-service orchestration (compose/helm/k8s).",
     r"(^|/)(docker-compose[^/]*|compose\.ya?ml)$|(^|/)(helm|k8s|kubernetes|charts)/", None,
     "docker compose / helm chart / kubernetes manifests",
     "Bring the stack up with one orchestration command (compose up or helm install)."),
    ("CI pipeline", "Ships continuous-integration automation.",
     r"(^|/)\.github/workflows/[^/]+\.ya?ml$|(^|/)\.gitlab-ci\.yml$|(^|/)\.circleci/", None,
     "continuous integration / github actions / build pipeline",
     "Push a commit and confirm CI runs the test suite automatically."),
    ("release automation", "Automates releases/publishing (tagged builds, changelog, registry push).",
     r"(^|/)\.github/workflows/[^/]*(release|publish|deploy)[^/]*\.ya?ml$|(^|/)\.goreleaser|(^|/)\.releaserc", None,
     "release workflow / publish pipeline / goreleaser / semantic release",
     "Tag a version and confirm an automated release (artifact/registry/changelog) is produced."),
    ("config example", "Ships a copyable configuration template.",
     r"(^|/)\.env\.(example|sample|template)$|(^|/)[^/]*config[^/]*\.(example|sample|template)(\.[a-z]+)?$|(^|/)[^/]*\.example\.(json|ya?ml|toml|env)$", None,
     "env example / sample config / configuration template",
     "Copy the shipped config example, fill the minimum values, and boot successfully from it."),
    ("schema/data migrations", "Ships database/data migration machinery.",
     r"(^|/)(migrations?|alembic)/|(^|/)migrate\.[a-z]+$", None,
     "schema migration / database migration / alembic",
     "Run the migration command against an old-schema database and confirm it upgrades cleanly."),
    ("healthcheck endpoint", "Exposes a liveness/readiness signal.",
     None, HEALTH_RE,
     "healthcheck / liveness / readiness probe",
     "Hit the health endpoint (or healthcheck command) and confirm it reports status."),
    ("packaging metadata", "Installable via standard packaging (not just git clone).",
     r"(^|/)(pyproject\.toml|setup\.py|package\.json|Cargo\.toml|go\.mod|Gemfile|\.gemspec)$", None,
     "package metadata / installable package / distribution",
     "Install the tool through its package manager entry point and run the binary."),
    ("task runner", "Ships a developer task entry point (make/just/task).",
     r"(^|/)(Makefile|justfile|Taskfile\.ya?ml|makefile)$", None,
     "makefile / justfile / task runner / dev commands",
     "Run the default dev task (e.g. `make test`) and confirm it works from a fresh clone."),
    ("changelog/versioning", "Keeps a user-facing change history.",
     r"(^|/)CHANGELOG([^/]*)?$|(^|/)CHANGES\.(md|rst|txt)$", None,
     "changelog / release notes / version history",
     "Open the changelog and confirm the latest released version has an entry."),
    ("install script", "Ships a one-command installer.",
     r"(^|/)install\.(sh|ps1)$|(^|/)scripts?/install[^/]*$", None,
     "install script / one-line install / setup script",
     "Run the install script on a clean machine/container and confirm a working binary."),
    ("distribution channels", "Ships through OS package managers beyond the language manifest.",
     r"(^|/)Formula/[^/]+\.rb$|(^|/)HomebrewFormula/|(^|/)debian/control$|(^|/)manifests/.+\.ya?ml$"
     r"|(^|/)snapcraft\.yaml$|(^|/)PKGBUILD$|(^|/)[^/]*\.flatpak\.yml$|(^|/)flathub\.json$"
     r"|(^|/)[^/]+\.nuspec$|(^|/)\.goreleaser\.ya?ml$", None,
     "homebrew formula / debian package / winget manifest / system package manager",
     "Install the tool via a system package manager (brew/apt/winget/snap) and run the installed binary."),
    ("changelog discipline", "Changelog follows a structured, dated, sectioned format (releases as a user contract).",
     None,
     r"## \[?[0-9]+\.[0-9]+[^]]*\]? - [0-9]{4}-|\[Unreleased\]|### (Added|Changed|Deprecated|Removed|Fixed|Security)",
     "keep a changelog / dated release headings / sectioned release notes",
     "Open the changelog and confirm the latest release has a dated version heading with change-type sections."),
    ("migration/upgrade guides", "Supports users through breaking changes (upgrade guides / deprecation lifecycle).",
     r"(^|/)UPGRADING[^/]*\.md$|(^|/)MIGRATION[^/]*\.md$|(^|/)docs/.*[Uu]pgrad|(^|/)docs/.*[Mm]igrat",
     r"deprecated in [0-9]|will be removed in|DeprecationWarning|#\[deprecated|@[Dd]eprecated",
     "upgrade guide / migration guide / deprecation policy",
     "Follow the upgrade guide across one breaking version bump and confirm the documented steps work."),
    ("telemetry/observability instrumentation", "Instruments itself (metrics/traces/structured logs), not just prints.",
     None,
     r"opentelemetry|prometheus[-_]client|prom-client|statsd|dogstatsd|structlog|tracing::|zap\.New",
     "metrics / tracing / structured logging / observability",
     "Run the service and confirm metrics or traces are emitted to the configured sink."),
    ("CLI polish (completions/man pages)", "Ships shell completions and/or man pages.",
     r"(^|/)completions?/[^/]+|(^|/)man/[^/]+|(^|/)(?!v?\d+(\.\d+)*\.)[^/]+\.(1|1\.md|ronn)$",
     r"gen_completions|clap_complete|GenBashCompletion|shtab",  # NOT generate_completion: LLM-completion vocabulary collision
     "shell completions / man pages / cli ergonomics",
     "Install the shipped shell completion (or open the man page) and confirm it works for the binary."),
]

# Content-grep hygiene (earned live on the telegram neighbors, 2026-06-11): lockfiles list
# transitive deps, so an opentelemetry line in uv.lock is not instrumentation; `### Added`
# headings appear in arbitrary docs, so changelog discipline must come from a changelog-shaped
# path; deprecation markers in source code are not user-facing upgrade support.
LOCKFILE_RE = re.compile(r"(^|/)[^/]*\.(lock|sum)$|(^|/)package-lock\.json$|(^|/)pnpm-lock\.ya?ml$")
VENDORED_RE = re.compile(r"\.min\.(js|css)$|\.(iife|umd|bundle)\.js$"
                         r"|(^|/)(vendor|vendored|third_party|node_modules|dist|build)/")
CONTENT_PATH_FILTERS = {
    "changelog discipline":
        re.compile(r"(^|/)(CHANGELOG|CHANGES|HISTORY|RELEASE[-_]?NOTES)[^/]*$|(^|/)changelogs?/", re.I),
    "migration/upgrade guides": re.compile(r"\.(md|rst|txt|mdx)$", re.I),
}


def filter_content_hit(cat, paths):
    """First content-grep hit that survives hygiene: lockfiles never count as evidence, and
    probes listed in CONTENT_PATH_FILTERS only accept hits from matching paths (pure)."""
    flt = CONTENT_PATH_FILTERS.get(cat)
    for p in paths:
        if LOCKFILE_RE.search(p) or VENDORED_RE.search(p) or (flt and not flt.search(p)):
            continue
        return p
    return None


def detect(files, health_hit=None, content_hits=None):
    """Probe a neighbor's tracked-file list (+ content-grep hits) -> {category: example_path} (pure).

    content_hits: {category: example_path} from the per-repo content greps (see main()).
    health_hit: kept as the original call shape for the healthcheck probe; folded into
    content_hits. Path hit wins when a probe declares both a path and a content regex.
    """
    hits = dict(content_hits or {})
    if health_hit:
        hits.setdefault("healthcheck endpoint", health_hit)
    found = {}
    for cat, _what, pat, content_re, _al, _tell in PROBES:
        if pat is not None:
            rx = re.compile(pat)
            hit = next((f for f in files if rx.search(f)), None)
            if hit:
                found[cat] = hit
                continue
        if content_re is not None and hits.get(cat):
            found[cat] = hits[cat]
    return found


def aggregate(per_neighbor):
    """{neighbor: {category: example}} -> checklist categories with convergence tiers (pure)."""
    cats = []
    for cat, what, _pat, _cre, aliases, tell in PROBES:
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


def capability_map():
    return {"tool": "surface_mine", "version": "0.1", "lens": "operability-surface",
            "axis": "OPERABILITY", "deterministic": True,
            "args": "<neighbor-repo-dir>... [--app-type T] [--emit PATH] [--json]",
            "probes": [p[0] for p in PROBES],
            "gating": "OPERABILITY is advisory in check.py until it beats the generic-baseline control",
            "exit_codes": {"0": "ok", "1": "usage/err", "2": "not_found", "3": "empty"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repos", nargs="*")
    ap.add_argument("--app-type", default="ai-agent-tool")
    ap.add_argument("--emit", metavar="PATH")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not a.repos:
        if a.json:
            print(json.dumps(capability_map())); sys.exit(EXIT_OK)
        print(capability_map()["args"], file=sys.stderr); sys.exit(EXIT_ERR)

    per_neighbor = {}
    for repo in a.repos:
        files = _git(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
        if not files:
            print(f"not a readable git repo: {repo}", file=sys.stderr); sys.exit(EXIT_NOT_FOUND)
        content_hits = {}
        for cat, _what, _pat, content_re, _al, _tell in PROBES:
            if content_re is None:
                continue
            grep = _git(repo, "grep", "-lIE", content_re, "HEAD").splitlines()
            hit = filter_content_hit(cat, [g.split(":", 1)[-1] for g in grep])
            if hit:
                content_hits[cat] = hit
        per_neighbor[neighbor_name(repo)] = detect(files, content_hits=content_hits)

    cats = aggregate(per_neighbor)
    if not cats:
        print("no operability artifacts detected in any neighbor", file=sys.stderr); sys.exit(EXIT_EMPTY)

    derived = sorted(per_neighbor)
    required = [c for c in cats if c["tier"] == "required"]
    optional = [c for c in cats if c["tier"] == "optional"]
    checklist = {
        "app_type": a.app_type,
        "lens": "operability-surface",
        "axis": "OPERABILITY",
        "scope_note": (f"OPERABILITY-axis spine for {a.app_type}: deterministic artifact-presence "
                       f"mining over {derived} — what mature neighbors ship AROUND the code. "
                       f"Advisory in check.py until this lens beats the generic-baseline control."),
        "derived_from": derived,
        "required": required,
        "optional": optional,
    }
    if a.emit:
        write_atomic(Path(a.emit), json.dumps(checklist, indent=2))
        print(f"→ {a.app_type} operability spine: {len(required)} convergent + {len(optional)} "
              f"single-neighbor → {a.emit}", file=sys.stderr)
    if a.json:
        print(json.dumps(checklist, indent=2)); sys.exit(EXIT_OK)

    print(f"=== {a.app_type} OPERABILITY spine (deterministic) ===")
    print(f"derived from: {derived}\n")
    for c in required:
        print(f"  🔁 {c['category']}  {c['projects']}  (e.g. {c['example']})")
    for c in optional:
        print(f"  ·  {c['category']}  {c['projects']}")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
