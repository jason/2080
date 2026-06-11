#!/usr/bin/env -S uv run --python 3.13
"""
lens_mine.py — 2080's multi-lens spine miner (formerly feature_mine.py).

One synthesis pipeline, many lenses: each LENSES entry is a source extractor + abstraction
prose; everything else (cross-neighbor synthesis, convergence tiering, day-1 tells, checklist
emission) is shared. Current lenses/axes:

  feature-surface    → SCOPE       product capabilities (README + feat: commits) — GATES (+0.27)
  robustness-surface → ROBUSTNESS  capability-phrased hardening (fix-commit subjects) — the
                                   experiment vehicle to supersede cluster_fixes' change-shaped labels
  issue-surface      → ISSUES      gaps users actually hit (GitHub issues) — GATES (+0.41 ×3, 2026-06-11)
  config-surface     → CONFIG      knob groups (config files + recurring env keys)
  test-surface       → TESTS       verification surface (test files + names)
  docs-surface       → DOCS        support surface (markdown headings)

The deterministic operability-surface lens (file-presence probes, no LLM) lives in
surface_mine.py. cluster_fixes.py is the original embedding/DBSCAN robustness mine —
superseded-pending-measurement by robustness-surface here (see its docstring).

None of these predict a project's SPECIFIC product bets — that's strategy, not completeness,
and is deliberately out of scope. An axis gates only after beating the generic-baseline control
in measure.py (check.py VALIDATED_GATING_AXES — currently SCOPE and ISSUES); the rest are advisory.

Emits a checklist-compatible JSON (required/optional + day1_tell) so `diff_target.py` consumes it
unchanged.

Usage:
  lens_mine.py <neighbor-repo-dir>... [--app-type T] [--lens NAME]
                  [--emit checklists/<app-type>.<lens>.json] [--json]
Exit codes: 0 OK | 1 USAGE/ERR | 2 NOT_FOUND | 3 EMPTY
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys
from pathlib import Path

from mine_common import fan_batch, extract_json, EXIT_OK, EXIT_ERR, EXIT_NOT_FOUND, EXIT_EMPTY

README_NAMES = ("README.md", "Readme.md", "readme.md", "README.rst", "README")


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True).stdout


def neighbor_name(repo_dir):
    n = Path(repo_dir).name
    for suf in ("-bt", "-harvest", ".git"):
        if n.endswith(suf):
            n = n[: -len(suf)]
    return n


# ── LENS registry ─────────────────────────────────────────────────────────────
# To add a mining dimension: register a lens here. `source(repo)` returns that repo's raw
# material as ONE text block; `material_label` + `abstract` parameterize the shared synthesis
# prompt. Aggregation (convergence tiering) and day-1 tells are lens-agnostic in main().
#
# GATING DISCIPLINE: only the SCOPE axis has beaten the generic-baseline control (+0.27) and
# earned the right to gate. Every other axis ships ADVISORY (check.py demotes it) until it
# passes the same measure.py control. Do not mark a new lens SCOPE to make it gate.

def _ls_tree(repo):
    return _git(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines()


def _grep_lines(repo, pattern, *pathspecs, cap=150):
    out = _git(repo, "grep", "-hIE", pattern, "HEAD", "--", *pathspecs) if pathspecs else \
        _git(repo, "grep", "-hIE", pattern, "HEAD")
    lines = [ln.split(":", 1)[-1].strip() for ln in out.splitlines()]
    seen, uniq = set(), []
    for ln in lines:
        if ln and ln not in seen:
            seen.add(ln); uniq.append(ln)
    return uniq[:cap]


def _feature_surface_source(repo):
    readme = ""
    for n in README_NAMES:
        r = _git(repo, "show", f"HEAD:{n}")
        if r:
            readme = r[:1400]
            break
    feats = [s for s in _git(repo, "log", "--format=%s").splitlines() if s.lower().startswith("feat")][:35]
    return f"README:\n{readme}\nfeat: commits:\n" + "\n".join(feats)


def norm_name(n):
    """Neighbor-name normalization for attribution matching (pure): 'Open-Interpreter' ==
    'openinterpreter' == 'open_interpreter'."""
    return re.sub(r"[^a-z0-9]", "", str(n).lower())


def slug_from_url(url):
    """github remote URL (https or ssh) -> 'owner/repo', or None (pure)."""
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url or "")
    return f"{m.group(1)}/{m.group(2)}" if m else None


def format_issue_lines(items, cap=120):
    """GitHub issues API items -> material lines, PRs excluded, reactions surfaced (pure)."""
    lines = []
    for it in items:
        if not isinstance(it, dict) or "pull_request" in it or not it.get("title"):
            continue
        n = (it.get("reactions") or {}).get("total_count", 0)
        lines.append(f"- [{it.get('state', '?')}] (+{n}) {str(it['title']).strip()[:120]}")
    lines.sort(key=lambda l: -int(re.search(r"\(\+(\d+)\)", l).group(1)))
    return lines[:cap]


FIX_SUBJECT_RE = re.compile(r"^(fix|bug|hotfix|patch)\b|(\bfix(es|ed)?\b)", re.I)


def _robustness_surface_source(repo):
    """Fix-shaped commit subjects — same raw material as cluster_fixes, but abstracted by the
    synthesis prompt into CAPABILITY-phrased categories instead of change-shaped cluster labels."""
    subs = [s for s in _git(repo, "log", "--format=%s", "-500").splitlines()
            if FIX_SUBJECT_RE.search(s)][:80]
    return "\n".join(subs)


def _issue_surface_source(repo):
    """Issues = gaps users EXPERIENCED. Fetched via gh, cached; empty block if gh/remote fails
    (the lens then just sees fewer neighbors — never crashes the mine)."""
    name = neighbor_name(repo)
    cache = Path(os.environ.get("CACHE_2080", os.path.expanduser("~/.cache/2080"))) / "issues"
    cache.mkdir(parents=True, exist_ok=True)
    cached = cache / f"{name}.json"
    if cached.exists():
        items = json.loads(cached.read_text())
    else:
        slug = slug_from_url(_git(repo, "remote", "get-url", "origin").strip())
        if not slug:
            return ""
        items = []
        for page in (1, 2):
            r = subprocess.run(["gh", "api", f"repos/{slug}/issues?state=all&per_page=100&page={page}"],
                               capture_output=True, text=True)
            if r.returncode != 0:
                break
            items += json.loads(r.stdout)
        cached.write_text(json.dumps(items))
    return "\n".join(format_issue_lines(items))


CONFIG_FILE_RE = re.compile(r"(^|/)(\.env[^/]*|docker-compose[^/]*|compose\.ya?ml|[^/]*config[^/]*\."
                            r"(example|sample|ya?ml|toml|json)|[^/]*\.example\.[^/]+)$", re.I)
ENV_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+){1,}\b")


def config_material(files, blobs):
    """Config filenames + recurring env-var tokens from their contents (pure)."""
    cfg_files = [f for f in files if CONFIG_FILE_RE.search(f)][:40]
    counts = {}
    for text in blobs:
        for tok in set(ENV_TOKEN_RE.findall(text or "")):
            counts[tok] = counts.get(tok, 0) + 1
    toks = sorted(counts, key=lambda t: -counts[t])[:80]
    return "config files:\n" + "\n".join(cfg_files) + "\nconfig keys:\n" + "\n".join(toks)


def _config_surface_source(repo):
    files = _ls_tree(repo)
    cfg = [f for f in files if CONFIG_FILE_RE.search(f)][:25]
    blobs = [_git(repo, "show", f"HEAD:{f}")[:6000] for f in cfg]
    return config_material(files, blobs)


TEST_PATH_RE = re.compile(r"(^|/)(tests?|spec|__tests__)(/|_)|[._-](test|spec)s?\.[a-z]+$|_test\.[a-z]+$", re.I)


def _test_surface_source(repo):
    tfiles = [f for f in _ls_tree(repo) if TEST_PATH_RE.search(f)]
    names = _grep_lines(repo, r"def test_|it\(['\"]|test\(['\"]|describe\(['\"]|#\[test\]|func Test",
                        *(tfiles[:200] or ["."]), cap=120) if tfiles else []
    return "test files:\n" + "\n".join(tfiles[:60]) + "\ntest names:\n" + "\n".join(names)


def _docs_surface_source(repo):
    heads = _grep_lines(repo, r"^#{1,3} ", "*.md", "*.rst", cap=150)
    return "doc headings:\n" + "\n".join(heads)


LENSES = {
    "feature-surface": {
        "axis": "SCOPE",
        "desc": "product capabilities a mature <app_type> converges on (README + feat: commits)",
        "source": _feature_surface_source,
        "material_label": "FEATURE surfaces (README + feat: commits)",
        "abstract": ("the product CAPABILITIES a full working {app_type} converges on — actual "
                     "user-facing features/capabilities, NOT bug-fixes or hardening"),
        "day1_kind": "reveals whether a product HAS this capability (e.g. 'open the web UI and confirm it "
                     "serves the chat interface', 'list configured providers and switch model mid-session')",
    },
    "robustness-surface": {
        "axis": "ROBUSTNESS",
        "desc": "capability-phrased hardening a mature <app_type> converges on (fix commits)",
        "source": _robustness_surface_source,
        "material_label": "FIX surfaces (fix-shaped commit subjects)",
        "abstract": ("the ROBUSTNESS CAPABILITIES a mature {app_type} converges on. CRITICAL: phrase "
                     "every category as a CAPABILITY the target either has or lacks ('recovers from "
                     "dropped connections mid-stream', 'splits messages exceeding platform limits') — "
                     "NEVER as a change or fix ('dependency fix', 'error handling improvement'). A "
                     "category must be judgeable as covered/gap by inspecting a codebase once"),
        "day1_kind": "tests the capability directly (e.g. 'kill the network mid-request and confirm "
                     "the bot reports a clean error instead of hanging')",
    },
    "issue-surface": {
        "axis": "ISSUES",
        "desc": "gaps users actually hit or demanded (GitHub issues, reaction-weighted)",
        "source": _issue_surface_source,
        "material_label": "ISSUE surfaces (GitHub issue titles, [state] (+reactions))",
        "abstract": ("the capability gaps and demands USERS of a {app_type} actually experience — "
                     "recurring complaint/request themes, weighted toward high-reaction and recurring "
                     "issues, NOT one-off bug reports"),
        "day1_kind": "reveals whether the product would suffer this user-reported gap (e.g. 'send a "
                     "long message and confirm it is split, not truncated')",
    },
    "config-surface": {
        "axis": "CONFIG",
        "desc": "configuration knobs a mature <app_type> exposes (config files + env keys)",
        "source": _config_surface_source,
        "material_label": "CONFIG surfaces (config filenames + recurring config/env keys)",
        "abstract": ("the CONFIGURATION capabilities a mature {app_type} exposes — groups of knobs "
                     "(timeouts, proxies, rate limits, credentials, model selection…), NOT individual "
                     "variable names"),
        "day1_kind": "reveals whether the knob group exists (e.g. 'set the request timeout in config and "
                     "confirm a slow call honors it')",
    },
    "test-surface": {
        "axis": "TESTS",
        "desc": "behaviors mature <app_type>s actually test (test files + test names)",
        "source": _test_surface_source,
        "material_label": "TEST surfaces (test file paths + test case names)",
        "abstract": ("the VERIFICATION surface a mature {app_type} converges on — categories of "
                     "behavior the projects all bother to test (reconnects, rate limits, parsing edge "
                     "cases…), NOT individual test names"),
        "day1_kind": "names the test the target should have (e.g. 'a test that kills the connection "
                     "mid-stream and asserts recovery')",
    },
    "docs-surface": {
        "axis": "DOCS",
        "desc": "support/doc sections a mature <app_type> ships (markdown headings)",
        "source": _docs_surface_source,
        "material_label": "DOCS surfaces (markdown headings from README + docs)",
        "abstract": ("the SUPPORT surface a mature {app_type} documents — recurring doc sections "
                     "(installation matrix, configuration reference, troubleshooting, deployment, "
                     "FAQ…), NOT prose topics"),
        "day1_kind": "reveals whether the doc section exists and is real (e.g. 'open docs and find a "
                     "troubleshooting section that covers a failed connection')",
    },
    # deterministic operability-surface lens lives in surface_mine.py (no LLM needed)
}


def synth_prompt(materials, app_type, lens):
    """Shared spine-synthesis prompt; lenses differ only in material_label + abstract prose."""
    names = [m["name"] for m in materials]
    blocks = "".join(f"\n### {m['name']}:\n{m['block'][:1800]}\n" for m in materials)
    return (
        f"Below are the {lens['material_label']} of {len(materials)} mature {app_type} projects: "
        f"{', '.join(names)}.\n{blocks}\n\n"
        f"Abstract these into a category-level spine: {lens['abstract'].format(app_type=app_type)}. "
        f"The \"neighbors\" field is REQUIRED on every category: list exactly which of the named "
        f"projects' material shows it (at least one; convergence across projects is the point of "
        f"this analysis). Only reference these projects ({', '.join(names)}); invent no others.\n"
        'Return ONLY JSON: {"spine":[{"category":"short name","what":"one line",'
        f'"neighbors":["one or more of: {", ".join(names)}"]}}]}}'
    )


def capability_map():
    return {"tool": "lens_mine", "version": "0.2",
            "args": "<neighbor-repo-dir>... [--app-type T] [--lens NAME] [--emit PATH] [--json]",
            "lenses": {k: {"axis": v["axis"], "desc": v["desc"]} for k, v in LENSES.items()},
            "gating": "an axis gates only after beating the generic-baseline control (check.py "
                      "VALIDATED_GATING_AXES — currently SCOPE, ISSUES); other axes are advisory",
            "exit_codes": {"0": "ok", "1": "usage/err", "2": "not_found", "3": "empty"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repos", nargs="*", help="local git repo dirs of mature neighbors")
    ap.add_argument("--app-type", default="ai-agent-tool")
    ap.add_argument("--lens", default="feature-surface", choices=list(LENSES.keys()))
    ap.add_argument("--emit", metavar="PATH", help="write checklist-compatible feature spine JSON")
    ap.add_argument("--model", default="gpt-5.5")
    ap.add_argument("--provider", default="openai-codex")
    ap.add_argument("--reasoning", default="low")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not a.repos:
        if a.json:
            print(json.dumps(capability_map())); sys.exit(EXIT_OK)
        print(capability_map()["args"], file=sys.stderr); sys.exit(EXIT_ERR)

    lens = LENSES[a.lens]
    materials = []
    for repo in a.repos:
        if not (Path(repo) / ".git").exists() and not Path(repo).joinpath("HEAD").exists():
            # allow bare or worktree; only hard-fail if git can't read it
            if not _git(repo, "rev-parse", "HEAD").strip():
                print(f"not a readable git repo: {repo}", file=sys.stderr); sys.exit(EXIT_NOT_FOUND)
        materials.append({"name": neighbor_name(repo), "block": lens["source"](repo) or ""})

    materials = [m for m in materials if m["block"].strip()]
    if not materials:
        print(f"no {a.lens} material extracted from any neighbor", file=sys.stderr); sys.exit(EXIT_EMPTY)

    def _fan(calls, mt_default=2500):
        return fan_batch(calls, a.model, a.provider, a.reasoning)

    # 1) synthesize the spine across neighbors
    try:
        synth_txt = _fan([{"id": "spine", "prompt": synth_prompt(materials, a.app_type, lens), "maxTokens": 2500}])["spine"]
    except Exception as e:
        print(f"fan error: {e}", file=sys.stderr); sys.exit(EXIT_ERR)
    parsed = extract_json(synth_txt) or {}
    spine = parsed.get("feature_spine") or parsed.get("spine") or []
    if not spine:
        print("spine synthesis returned nothing parseable", file=sys.stderr); sys.exit(EXIT_EMPTY)

    # normalized matching: the model writes product names ("open-interpreter", "Aider"); the
    # canonical names are clone-dir names ("openinterpreter") — exact match silently dropped
    # every attribution and zeroed the required tier (caught live 2026-06-11).
    canon = {norm_name(m["name"]): m["name"] for m in materials}
    cats = []
    for c in spine:
        neighs = sorted({canon[norm_name(n)] for n in (c.get("neighbors") or [])
                         if norm_name(n) in canon})
        cats.append({"category": str(c.get("category", "")).strip(),
                     "what": str(c.get("what", "")).strip(),
                     "projects": neighs,
                     "recurrence_projects": len(neighs),
                     # CONVERGENCE tiering: a capability ≥2 neighbors share is "required scope";
                     # a single-neighbor capability is "optional" (one project's bet).
                     "tier": "required" if len(neighs) >= 2 else "optional"})
    cats = [c for c in cats if c["category"]]

    # 2) day-1 tells (one fan call, batched per category)
    listing = "\n".join(f"{i+1}. {c['category']} — {c['what']}" for i, c in enumerate(cats))
    tell_prompt = ("For each numbered product capability, write ONE concrete DAY-1 CHECK that "
                   f"{lens['day1_kind']}. Return ONLY JSON {{number: check}}.\n\n" + listing)
    try:
        tells = extract_json(_fan([{"id": "tells", "prompt": tell_prompt, "maxTokens": max(1500, len(cats) * 60)}])["tells"]) or {}
    except Exception:
        tells = {}
    for i, c in enumerate(cats):
        c["day1_tell"] = str(tells.get(str(i + 1)) or tells.get(i + 1) or "").strip()

    derived = sorted(m["name"] for m in materials)
    required = [c for c in cats if c["tier"] == "required"]
    optional = [c for c in cats if c["tier"] == "optional"]
    checklist = {
        "app_type": a.app_type,
        "lens": a.lens,
        "axis": lens["axis"],
        "scope_note": (f"{lens['axis']}-axis spine for {a.app_type}, mined via the {a.lens} lens "
                       f"({lens['desc'].replace('<app_type>', a.app_type)}) from {derived}. "
                       f"Does NOT predict project-specific product direction — that is strategy, not "
                       f"completeness. An axis gates only after beating the generic-baseline control "
                       f"(check.py VALIDATED_GATING_AXES); the rest are advisory."),
        "derived_from": derived,
        "required": required,
        "optional": optional,
    }

    if a.emit:
        Path(a.emit).write_text(json.dumps(checklist, indent=2))
        print(f"→ {a.app_type} feature spine ({a.lens}): {len(required)} convergent (required) + "
              f"{len(optional)} single-neighbor (optional) → {a.emit}", file=sys.stderr)

    if a.json:
        print(json.dumps(checklist, indent=2)); sys.exit(EXIT_OK)

    print(f"=== {a.app_type} spine [{lens['axis']} axis, lens={a.lens}] ===")
    print(f"derived from {a.lens} material of: {derived}\n")
    print(f"CONVERGENT capabilities (≥2 neighbors → required scope) — {len(required)}:")
    for c in required:
        print(f"  🔁 {c['category']}  {c['projects']}")
        if c["day1_tell"]:
            print(f"       ↳ day-1: {c['day1_tell'][:120]}")
    print(f"\nSINGLE-NEIGHBOR capabilities (optional) — {len(optional)}:")
    for c in optional:
        print(f"  ·  {c['category']}  {c['projects']}")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
