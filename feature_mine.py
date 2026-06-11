#!/usr/bin/env -S uv run --python 3.13
"""
feature_mine.py — 2080's SCOPE-completeness mine (the feature-surface lens).

The sibling of `cluster_fixes.py`. They mine neighbor history along two different AXES:

  cluster_fixes.py  — recurring-FIX lens   → ROBUSTNESS spine
        "what hardening do mature <app_type> repos converge on?" (telemetry, retry, validation…)
        Clusters recurring *fixes*; what recurs across repos is the infra skeleton.

  feature_mine.py   — feature-SURFACE lens → SCOPE spine   ← THIS FILE
        "what CAPABILITIES does a full working <app_type> need?" (multi-provider, web UI,
        plugin system, auth flow…). Reads each neighbor's README + feat: commits and abstracts
        to a category-level feature spine, tiered by cross-neighbor CONVERGENCE.

Why two mines: a blind backtest on dexto showed the recurring-fix spine is 100% robustness and
recalls ~0 of later product features; the feature-surface spine recalls the generic-scope features
(provider matrix, WebUI, plugins, auth) the robustness engine misses. Neither predicts a project's
SPECIFIC product bets (multimodal, subagents, vertical agents) — that's strategy, not completeness,
and is deliberately out of scope.

LENS is the extension seam: a new mining dimension (integration-surface, threat-surface,
operability-surface, …) is a new entry in LENSES — source selector + abstraction instruction —
not new plumbing. See mine_common.py.

Emits a checklist-compatible JSON (required/optional + day1_tell) so `diff_target.py` consumes it
unchanged.

Usage:
  feature_mine.py <neighbor-repo-dir>... [--app-type T] [--lens feature-surface]
                  [--emit checklists/<app-type>.features.json] [--json]
Exit codes: 0 OK | 1 USAGE/ERR | 2 NOT_FOUND | 3 EMPTY
"""
from __future__ import annotations
import argparse, json, subprocess, sys
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
# To add a mining dimension: register a lens here. `source(repo)` returns the raw material;
# `synth(material, app_type)` returns the spine-synthesis prompt. Aggregation (convergence
# tiering) and day-1 tells are lens-agnostic and handled in main().

def _feature_surface_source(repo):
    readme = ""
    for n in README_NAMES:
        r = _git(repo, "show", f"HEAD:{n}")
        if r:
            readme = r[:1800]
            break
    feats = [s for s in _git(repo, "log", "--format=%s").splitlines() if s.lower().startswith("feat")][:45]
    return {"readme": readme, "feat_commits": feats}


def _feature_surface_synth(materials, app_type):
    blocks = ""
    for m in materials:
        blocks += (f"\n### {m['name']} README:\n{m['readme'][:1400]}\n"
                   f"### {m['name']} feat: commits:\n" + "\n".join(m["feat_commits"][:35]) + "\n")
    names = [m["name"] for m in materials]
    return (
        f"Below are the FEATURE surfaces (README + feat: commits) of {len(materials)} mature "
        f"{app_type} projects: {', '.join(names)}.\n{blocks}\n\n"
        f"Abstract these into a category-level FEATURE SPINE: the product CAPABILITIES a full working "
        f"{app_type} converges on — actual user-facing features/capabilities, NOT bug-fixes or hardening. "
        f"For each category, note which of the named projects have it. Only reference these projects "
        f"({', '.join(names)}); invent no others.\n"
        'Return ONLY JSON: {"feature_spine":[{"category":"short name","what":"one line","neighbors":["..."]}]}'
    )


LENSES = {
    "feature-surface": {
        "axis": "SCOPE",
        "desc": "product capabilities a mature <app_type> converges on (README + feat: commits)",
        "source": _feature_surface_source,
        "synth": _feature_surface_synth,
        "day1_kind": "reveals whether a product HAS this capability (e.g. 'open the web UI and confirm it "
                     "serves the chat interface', 'list configured providers and switch model mid-session')",
    },
    # future: "integration-surface" (SCOPE), "threat-surface" (SECURITY), "operability-surface" (OPS)…
}


def capability_map():
    return {"tool": "feature_mine", "version": "0.1",
            "args": "<neighbor-repo-dir>... [--app-type T] [--lens feature-surface] [--emit PATH] [--json]",
            "lenses": list(LENSES.keys()),
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
        src = lens["source"](repo)
        src["name"] = neighbor_name(repo)
        materials.append(src)

    if not any(m.get("readme") or m.get("feat_commits") for m in materials):
        print("no feature material extracted from any neighbor", file=sys.stderr); sys.exit(EXIT_EMPTY)

    def _fan(calls, mt_default=2500):
        return fan_batch(calls, a.model, a.provider, a.reasoning)

    # 1) synthesize the spine across neighbors
    try:
        synth_txt = _fan([{"id": "spine", "prompt": lens["synth"](materials, a.app_type), "maxTokens": 2500}])["spine"]
    except Exception as e:
        print(f"fan error: {e}", file=sys.stderr); sys.exit(EXIT_ERR)
    parsed = extract_json(synth_txt) or {}
    spine = parsed.get("feature_spine") or parsed.get("spine") or []
    if not spine:
        print("spine synthesis returned nothing parseable", file=sys.stderr); sys.exit(EXIT_EMPTY)

    names = {m["name"] for m in materials}
    cats = []
    for c in spine:
        neighs = [n for n in (c.get("neighbors") or []) if n in names]
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

    derived = sorted(names)
    required = [c for c in cats if c["tier"] == "required"]
    optional = [c for c in cats if c["tier"] == "optional"]
    checklist = {
        "app_type": a.app_type,
        "lens": a.lens,
        "axis": lens["axis"],
        "scope_note": (f"SCOPE-completeness spine for {a.app_type}, mined via the {a.lens} lens from the "
                       f"FEATURE surface of {derived}. Complements the robustness spine (cluster_fixes.py). "
                       f"Does NOT predict project-specific product direction — that is strategy, not completeness."),
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

    print(f"=== {a.app_type} FEATURE spine [{lens['axis']} axis, lens={a.lens}] ===")
    print(f"derived from feature surfaces of: {derived}\n")
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
