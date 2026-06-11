#!/usr/bin/env python3
"""
init.py — one-command matched-spine acquisition. `2080 init`: from "what am I building?"
to BOTH mined spines (robustness + scope) sitting in checklists/, ready for `check.py`.

Every stage already exists as its own tool — this is glue + caching, not new mining:

  intent     ← target dir's README first paragraph (deterministic), or the literal arg,
               or --intent. The intent is the steering input for everything downstream.
  neighbors  ← find_neighbors.py --json (LLM + gh), top --max-neighbors by MEASURED
               maturity. Or --neighbors owner/repo,... to skip discovery entirely.
  clone      ← ~/.cache/2080/neighbors/<name>, `git clone --filter=blob:none`: full commit
               HISTORY is required (subjects feed the mine) but blobs stay lazy; the README
               still materializes in the working tree for lens_mine.
  harvest    ← ~/.cache/2080/harvests/<name>.json {"project", "commits":[{"sha","subject"}]}
               — exactly cluster_fixes.py's input contract.
  mine       ← cluster_fixes.py  → checklists/<app_type>.robustness.json  (robustness spine)
               lens_mine.py   → checklists/<app_type>.features.json    (scope spine)

Clone + harvest are idempotent (re-run refreshes, never re-clones), so init doubles as the
"update my spines" command. A full live run costs ~30-60 min of LLM+network — hence --dry-run
prints the complete plan with zero network/LLM, and any write requires confirmation (--yes in
--json mode, prompt otherwise).

Usage:
  init.py <target-dir | "intent string"> [--intent S] [--max-neighbors N]
          [--neighbors owner/repo,...] [--app-type T] [--max-commits N]
          [--skip-robustness] [--skip-scope] [--dry-run] [--json] [--yes]
Exit codes: 0 OK | 1 USAGE/ERR/DECLINED | 2 NOT_FOUND | 3 EMPTY (no neighbors/commits)
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys
from pathlib import Path

from mine_common import extract_json, EXIT_OK, EXIT_ERR, EXIT_NOT_FOUND, EXIT_EMPTY

SCRIPT_DIR = Path(__file__).resolve().parent
CACHE_ROOT = Path(os.environ.get("CACHE_2080", str(Path.home() / ".cache" / "2080")))
README_NAMES = ("README.md", "Readme.md", "readme.md", "README.rst", "README")
REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")  # also blocks ../ path traversal into the cache


def capability_map():
    return {"tool": "2080-init", "version": "0.2",
            "args": '<target-dir | "intent string"> [--intent S] [--max-neighbors N] '
                    '[--neighbors owner/repo,...] [--app-type T] [--max-commits N] '
                    '[--skip-robustness] [--skip-scope] [--dry-run] [--force] [--json] [--yes]',
            "exit_codes": {"0": "ok", "1": "usage/err/declined/would-overwrite", "2": "not_found",
                           "3": "empty (no neighbors or no commits)"}}


def fail(msg, code, as_json):
    if as_json:
        print(json.dumps({"ok": False, "error": msg, "exit_code": code}), file=sys.stderr)
    else:
        print(msg, file=sys.stderr)
    sys.exit(code)


# ── stage 1: intent ───────────────────────────────────────────────────────────

def first_readme_paragraph(text):
    """Deterministic intent from a README: first prose paragraph (headings, badges,
    images, HTML skipped; blockquote taglines count as prose)."""
    for block in re.split(r"\n\s*\n", text or ""):
        keep = []
        for line in block.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith(("[![", "![", "<", "---", "===")):
                continue
            keep.append(line.lstrip("> ").strip())
        keep = [k for k in keep if k]
        if keep:
            para = re.sub(r"\s+", " ", " ".join(keep)).replace("**", "").replace("`", "")
            return para[:300]
    return None


def resolve_intent(arg, override):
    """arg is a directory → derive intent from its README (overridable); else arg IS the intent.
    Returns (intent, target_dir|None); raises SystemExit-shaped tuple via ValueError on miss."""
    p = Path(arg)
    if p.is_dir():
        if override:
            return override, p
        for name in README_NAMES:
            rp = p / name
            if rp.is_file():
                intent = first_readme_paragraph(rp.read_text(errors="replace"))
                if intent:
                    return intent, p
        raise FileNotFoundError(f"no usable README in {arg} — pass --intent \"...\"")
    return (override or arg), None


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower())[:40].strip("-") or "project"


# ── stage 2: neighbors ────────────────────────────────────────────────────────

def discover_neighbors(intent):
    """find_neighbors.py --json (LLM + gh). Returns its parsed output dict."""
    r = subprocess.run([str(SCRIPT_DIR / "find_neighbors.py"), intent, "--json"],
                       capture_output=True, text=True, timeout=900)
    out = extract_json(r.stdout)
    if not out or r.returncode != 0:
        raise RuntimeError(f"find_neighbors failed: {(r.stderr or r.stdout or '')[:300]}")
    return out


# ── stage 3: clone (idempotent) ───────────────────────────────────────────────

def clone_dest(repo):
    return CACHE_ROOT / "neighbors" / repo.split("/")[-1]


def ensure_clone(repo, dest, run=subprocess.run):
    """Idempotent: clone --filter=blob:none if absent (full history, lazy blobs);
    fetch + ff-merge to refresh if present. Returns 'cloned' | 'refreshed'."""
    if (dest / ".git").exists():
        run(["git", "-C", str(dest), "fetch", "--quiet"], capture_output=True, text=True)
        run(["git", "-C", str(dest), "merge", "--ff-only", "--quiet", "FETCH_HEAD"],
            capture_output=True, text=True)  # best-effort; diverged/detached just stays put
        return "refreshed"
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = run(["git", "clone", "--filter=blob:none", f"https://github.com/{repo}.git", str(dest)],
            capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"clone failed for {repo}: {(r.stderr or '')[:200]}")
    return "cloned"


# ── stage 4: harvest ──────────────────────────────────────────────────────────

def build_harvest(clone_dir, name, max_commits=500):
    """git log subjects → cluster_fixes.py's exact input shape (newest first)."""
    cmd = ["git", "-C", str(clone_dir), "log", "--format=%H%x09%s"]
    if max_commits:
        cmd += ["-n", str(max_commits)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    commits = []
    for line in r.stdout.splitlines():
        sha, _, subject = line.partition("\t")
        if sha and subject.strip():
            commits.append({"sha": sha, "subject": subject.strip()})
    return {"project": name, "commits": commits}


# ── stage 5: mine (delegate; never reimplement) ───────────────────────────────

def _tool_cmd(script):
    p = SCRIPT_DIR / script
    return [str(p)] if os.access(p, os.X_OK) else ["uv", "run", "--python", "3.13", str(p)]


def run_mine(cmd, as_json):
    """Run a miner; in --json mode its stdout must not pollute ours → route to stderr."""
    r = subprocess.run(cmd, stdout=(sys.stderr if as_json else None), stderr=None, text=True)
    return r.returncode == 0


# ── orchestration ─────────────────────────────────────────────────────────────

def spine_paths(app_type):
    d = SCRIPT_DIR / "checklists"
    return (d / f"{app_type}.robustness.json", d / f"{app_type}.features.json",
            d / f"{app_type}.operability.json")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("target", nargs="?", help='target repo dir, or an "intent" string')
    ap.add_argument("--intent", help="override the derived intent")
    ap.add_argument("--max-neighbors", type=int, default=4, help="top N discovered neighbors by maturity")
    ap.add_argument("--neighbors", help="owner/repo,... — override discovery (skips the find_neighbors LLM step)")
    ap.add_argument("--app-type", help="spine label; default from discovery (slug of intent with --neighbors)")
    ap.add_argument("--max-commits", type=int, default=500, help="newest commits harvested per neighbor (0 = all)")
    ap.add_argument("--skip-robustness", action="store_true", help="skip the cluster_fixes robustness mine")
    ap.add_argument("--skip-scope", action="store_true", help="skip the lens_mine scope mine")
    ap.add_argument("--dry-run", action="store_true", help="print the full plan; NO network/LLM, NO writes")
    ap.add_argument("--force", action="store_true", help="overwrite existing spine files for this app-type")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--yes", "-y", action="store_true", help="proceed without confirmation (required for writes in --json mode)")
    a = ap.parse_args()

    if not a.target:
        if a.json:
            print(json.dumps(capability_map())); sys.exit(EXIT_OK)
        print(capability_map()["args"], file=sys.stderr); sys.exit(EXIT_ERR)

    try:
        intent, target_dir = resolve_intent(a.target, a.intent)
    except FileNotFoundError as e:
        fail(str(e), EXIT_NOT_FOUND, a.json)

    override = [s.strip() for s in (a.neighbors or "").split(",") if s.strip()]
    for repo in override:
        if not REPO_RE.fullmatch(repo):
            fail(f"bad --neighbors entry (want owner/repo): {repo}", EXIT_ERR, a.json)

    next_target = str(target_dir) if target_dir else "<your-repo>"

    # ── dry-run: the complete plan, zero network/LLM, zero writes ──
    if a.dry_run:
        app_type = a.app_type or (slug(intent) if override else "<app_type from find_neighbors>")
        rob, feat, ops = spine_paths(app_type)
        plan = {"ok": True, "dry_run": True, "intent": intent, "target": next_target,
                "app_type": app_type,
                "neighbors": override or f"<discover: find_neighbors.py \"{intent}\" --json, top {a.max_neighbors} by maturity>",
                "would_clone": ([str(clone_dest(r)) for r in override]
                                or f"{CACHE_ROOT}/neighbors/<name> per neighbor (git clone --filter=blob:none, idempotent)"),
                "would_harvest": f"{CACHE_ROOT}/harvests/<name>.json (newest {a.max_commits or 'all'} commit subjects)",
                "would_mine": {"robustness": "skipped" if a.skip_robustness else str(rob),
                               "scope": "skipped" if a.skip_scope else str(feat),
                               "operability": str(ops)},
                "next": f"check.py {next_target} --spine {feat if not a.skip_scope else rob}"}
        if a.json:
            print(json.dumps(plan, indent=2))
        else:
            print("DRY RUN — no network, no LLM, no writes. Plan:")
            for k in ("intent", "target", "app_type", "neighbors", "would_clone", "would_harvest"):
                print(f"  {k}: {plan[k]}")
            print(f"  would_mine: robustness={plan['would_mine']['robustness']}")
            print(f"              scope={plan['would_mine']['scope']}")
            print(f"  next: {plan['next']}")
        sys.exit(EXIT_OK)

    # ── writes ahead: enforce consent BEFORE spending LLM/network ──
    if a.json and not a.yes:
        fail("--yes is required to clone + mine in --json mode (use --dry-run for the plan)", EXIT_ERR, a.json)

    # ── stage 2: neighbors ──
    if override:
        neighbors = [{"repo": r, "why_valuable": "user-specified via --neighbors",
                      "maturity": {"label": "user", "commits": None}} for r in override]
        app_type, sub_type = a.app_type or slug(intent), None
    else:
        print(f"→ discovering neighbors for: {intent}", file=sys.stderr)
        try:
            found = discover_neighbors(intent)
        except Exception as e:
            fail(str(e), EXIT_ERR, a.json)
        neighbors = (found.get("neighbors") or [])[: a.max_neighbors]  # find_neighbors pre-sorts by measured maturity
        app_type, sub_type = a.app_type or found.get("app_type") or slug(intent), found.get("sub_type")
        if not neighbors:
            fail("find_neighbors returned no neighbors — refine the intent or pass --neighbors", EXIT_EMPTY, a.json)

    # ── overwrite guard: a colliding app_type label would silently clobber a different sub-type's
    # spine (sub-type match is load-bearing; an LLM-classified label is not unique). Refuse early.
    rob_guard, feat_guard, ops_guard = spine_paths(app_type)
    clobber = [str(p) for p, skip in ((rob_guard, a.skip_robustness), (feat_guard, a.skip_scope),
                                      (ops_guard, False))
               if not skip and p.exists()]
    if clobber and not a.force:
        fail(f"refusing to overwrite existing spine(s) for app_type '{app_type}': {', '.join(clobber)} "
             f"— pass --app-type <more-specific-label> (recommended) or --force", EXIT_ERR, a.json)

    listing = "\n".join(f"  {n['repo']}  [{(n.get('maturity') or {}).get('label')}: "
                        f"{(n.get('maturity') or {}).get('commits')} commits] — {n.get('why_valuable', '')[:90]}"
                        for n in neighbors)
    print(f"proposed neighbors (app_type={app_type}):\n{listing}", file=sys.stderr)
    if not a.yes:
        try:
            ans = input("Clone + mine these? [y/N] ").strip().lower()
        except EOFError:
            ans = ""
        if ans not in ("y", "yes"):
            fail("declined", EXIT_ERR, a.json)

    # ── stages 3+4: clone + harvest (idempotent) ──
    cloned, harvests = {}, {}
    harvest_dir = CACHE_ROOT / "harvests"
    harvest_dir.mkdir(parents=True, exist_ok=True)
    for n in neighbors:
        repo = n["repo"]
        if not REPO_RE.fullmatch(repo or ""):
            print(f"  ✗ skipping malformed repo name: {repo}", file=sys.stderr); continue
        name, dest = repo.split("/")[-1], clone_dest(repo)
        try:
            action = ensure_clone(repo, dest)
        except RuntimeError as e:
            print(f"  ✗ {e}", file=sys.stderr); continue
        cloned[name] = {"path": str(dest), "action": action}
        h = build_harvest(dest, name, a.max_commits)
        if not h["commits"]:
            print(f"  ✗ no commits harvested from {repo}", file=sys.stderr); continue
        hp = harvest_dir / f"{name}.json"
        hp.write_text(json.dumps(h))
        harvests[name] = {"path": str(hp), "commits": len(h["commits"])}
        print(f"  ✓ {repo}: {action}, {len(h['commits'])} commits → {hp}", file=sys.stderr)
    if not harvests:
        fail("no neighbor produced a harvest — nothing to mine", EXIT_EMPTY, a.json)

    # ── stage 5: mine the spines ──
    rob_path, feat_path, ops_path = spine_paths(app_type)
    rob_path.parent.mkdir(parents=True, exist_ok=True)
    spines = {}
    if a.skip_robustness:
        spines["robustness"] = "skipped"
    else:
        print(f"→ mining robustness spine (cluster_fixes) from {len(harvests)} harvests…", file=sys.stderr)
        ok = run_mine(_tool_cmd("cluster_fixes.py") + [h["path"] for h in harvests.values()]
                      + ["--app-type", app_type, "--emit-checklist", str(rob_path)], a.json)
        spines["robustness"] = {"path": str(rob_path), "ok": ok and rob_path.exists()}
    if a.skip_scope:
        spines["scope"] = "skipped"
    else:
        print(f"→ mining scope spine (lens_mine) from {len(cloned)} clones…", file=sys.stderr)
        ok = run_mine(_tool_cmd("lens_mine.py") + [c["path"] for c in cloned.values()]
                      + ["--app-type", app_type, "--emit", str(feat_path)], a.json)
        spines["scope"] = {"path": str(feat_path), "ok": ok and feat_path.exists()}
    # operability is deterministic and free (no LLM) — always mined, no skip flag needed
    print(f"→ mining operability spine (surface_mine, deterministic) from {len(cloned)} clones…", file=sys.stderr)
    ok = run_mine(_tool_cmd("surface_mine.py") + [c["path"] for c in cloned.values()]
                  + ["--app-type", app_type, "--emit", str(ops_path)], a.json)
    spines["operability"] = {"path": str(ops_path), "ok": ok and ops_path.exists()}

    mined = [s for s in spines.values() if isinstance(s, dict)]
    all_ok = bool(mined) and all(s["ok"] for s in mined)
    next_spine = feat_path if isinstance(spines["scope"], dict) and spines["scope"]["ok"] else rob_path
    out = {"ok": all_ok, "intent": intent, "target": next_target, "app_type": app_type,
           "sub_type": sub_type,
           "neighbors": [{"repo": n["repo"], "maturity": (n.get("maturity") or {}).get("label"),
                          "why": n.get("why_valuable", "")} for n in neighbors],
           "cloned": cloned, "harvests": harvests, "spines": spines,
           "next": f"check.py {next_target} --spine {next_spine}"}

    if a.json:
        print(json.dumps(out, indent=2)); sys.exit(EXIT_OK if all_ok else EXIT_ERR)
    print(f"\n{'✅' if all_ok else '⚠️ '} init {'complete' if all_ok else 'finished with errors'} — app_type={app_type}")
    for kind, s in spines.items():
        print(f"  {kind}: {s if isinstance(s, str) else (s['path'] if s['ok'] else 'FAILED: ' + s['path'])}")
    print(f"\nnext: {out['next']}")
    sys.exit(EXIT_OK if all_ok else EXIT_ERR)


if __name__ == "__main__":
    main()
