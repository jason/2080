#!/usr/bin/env python3
"""
surface_mine.py — the OPERABILITY lens, fully deterministic (no LLM, no cost).

What do mature neighbors ship AROUND the code: Dockerfile, compose, CI, release automation,
config example, migrations, healthcheck, packaging… This is classic second-85% material —
invisible in a demo, mandatory in production, highly convergent per app type — and it's pure
file-presence evidence, so mining it needs zero LLM calls and is exactly reproducible.

Each probe = one category. A neighbor "has" the category if any tracked path (or grepped
content, for healthcheck) matches. Convergence tiering matches the other mines: ≥2 neighbors →
required, 1 → optional. Emits a checklist-compatible spine with axis OPERABILITY — ADVISORY in
check.py (like every non-SCOPE axis) until this lens beats the generic-baseline control.

Usage: surface_mine.py <neighbor-repo-dir>... [--app-type T] [--emit PATH] [--json]
Exit codes: 0 OK | 1 USAGE/ERR | 2 NOT_FOUND | 3 EMPTY
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from pathlib import Path

from mine_common import EXIT_OK, EXIT_ERR, EXIT_NOT_FOUND, EXIT_EMPTY
from lens_mine import neighbor_name

# (category, what, path regex, aliases-for-evidence-grep, day1_tell)
PROBES = [
    ("containerization", "Ships a container image definition.",
     r"(^|/)(Dockerfile|Containerfile)(\.[^/]+)?$",
     "docker / container image / dockerfile",
     "Build the container image from the repo's Dockerfile and run it."),
    ("compose/orchestration", "Ships multi-service orchestration (compose/helm/k8s).",
     r"(^|/)(docker-compose[^/]*|compose\.ya?ml)$|(^|/)(helm|k8s|kubernetes|charts)/",
     "docker compose / helm chart / kubernetes manifests",
     "Bring the stack up with one orchestration command (compose up or helm install)."),
    ("CI pipeline", "Ships continuous-integration automation.",
     r"(^|/)\.github/workflows/[^/]+\.ya?ml$|(^|/)\.gitlab-ci\.yml$|(^|/)\.circleci/",
     "continuous integration / github actions / build pipeline",
     "Push a commit and confirm CI runs the test suite automatically."),
    ("release automation", "Automates releases/publishing (tagged builds, changelog, registry push).",
     r"(^|/)\.github/workflows/[^/]*(release|publish|deploy)[^/]*\.ya?ml$|(^|/)\.goreleaser|(^|/)\.releaserc",
     "release workflow / publish pipeline / goreleaser / semantic release",
     "Tag a version and confirm an automated release (artifact/registry/changelog) is produced."),
    ("config example", "Ships a copyable configuration template.",
     r"(^|/)\.env\.(example|sample|template)$|(^|/)[^/]*config[^/]*\.(example|sample|template)(\.[a-z]+)?$|(^|/)[^/]*\.example\.(json|ya?ml|toml|env)$",
     "env example / sample config / configuration template",
     "Copy the shipped config example, fill the minimum values, and boot successfully from it."),
    ("schema/data migrations", "Ships database/data migration machinery.",
     r"(^|/)(migrations?|alembic)/|(^|/)migrate\.[a-z]+$",
     "schema migration / database migration / alembic",
     "Run the migration command against an old-schema database and confirm it upgrades cleanly."),
    ("healthcheck endpoint", "Exposes a liveness/readiness signal.",
     None,  # content probe, see HEALTH_RE
     "healthcheck / liveness / readiness probe",
     "Hit the health endpoint (or healthcheck command) and confirm it reports status."),
    ("packaging metadata", "Installable via standard packaging (not just git clone).",
     r"(^|/)(pyproject\.toml|setup\.py|package\.json|Cargo\.toml|go\.mod|Gemfile|\.gemspec)$",
     "package metadata / installable package / distribution",
     "Install the tool through its package manager entry point and run the binary."),
    ("task runner", "Ships a developer task entry point (make/just/task).",
     r"(^|/)(Makefile|justfile|Taskfile\.ya?ml|makefile)$",
     "makefile / justfile / task runner / dev commands",
     "Run the default dev task (e.g. `make test`) and confirm it works from a fresh clone."),
    ("changelog/versioning", "Keeps a user-facing change history.",
     r"(^|/)CHANGELOG([^/]*)?$|(^|/)CHANGES\.(md|rst|txt)$",
     "changelog / release notes / version history",
     "Open the changelog and confirm the latest released version has an entry."),
    ("install script", "Ships a one-command installer.",
     r"(^|/)install\.(sh|ps1)$|(^|/)scripts?/install[^/]*$",
     "install script / one-line install / setup script",
     "Run the install script on a clean machine/container and confirm a working binary."),
]
HEALTH_RE = r"healthz|readyz|/health|health_check|healthcheck"


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True).stdout


def detect(files, health_hit):
    """Probe a neighbor's tracked-file list -> {category: example_path|True} (pure)."""
    found = {}
    for cat, _what, pat, _al, _tell in PROBES:
        if pat is None:
            if health_hit:
                found[cat] = health_hit
            continue
        rx = re.compile(pat)
        hit = next((f for f in files if rx.search(f)), None)
        if hit:
            found[cat] = hit
    return found


def aggregate(per_neighbor):
    """{neighbor: {category: example}} -> checklist categories with convergence tiers (pure)."""
    cats = []
    for cat, what, _pat, aliases, tell in PROBES:
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
        health = _git(repo, "grep", "-lIE", HEALTH_RE, "HEAD").splitlines()
        health_hit = health[0].split(":", 1)[-1] if health else None
        per_neighbor[neighbor_name(repo)] = detect(files, health_hit)

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
        Path(a.emit).write_text(json.dumps(checklist, indent=2))
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
