#!/usr/bin/env python3
"""
find_neighbors.py — 2080's METATOOL front-end.

Given WHAT you're building (intent), discover and JUSTIFY the mature similar repos worth
mining for a prior-art second-85% checklist. This is the layer that makes 2080 general
without a universal checklist: it builds the right neighbor set per request.

  intent --(fan/gpt-5.5)--> app_type + sub_type + GitHub search queries
         --(gh api)-------> candidate repos (real stars / activity)
         --(fan/gpt-5.5)--> evaluate each: genuine neighbor? sub-type match? mature? why valuable?
         ----------------> ranked, justified neighbor proposal (feeds harvest -> cluster -> checklist)

Usage: find_neighbors.py "what you are building" [--json]
"""
import argparse, json, re, subprocess, sys
from datetime import datetime, timezone

from mine_common import fan_call as mc_fan_call, extract_json


def _months_since(iso):
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - d).days / 30.0


def commit_count(full_name):
    """Cheap total-commit count via the Link rel=last header (per_page=1)."""
    try:
        r = subprocess.run(["gh", "api", "-i", f"repos/{full_name}/commits?per_page=1"],
                           capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return 0
    m = re.search(r'[?&]page=(\d+)>;\s*rel="last"', r.stdout)
    if m:
        return int(m.group(1))
    return 1 if '"sha"' in r.stdout else 0


def measured_maturity(cand):
    """Maturity from real gh data — NOT an LLM guess. Maturity is load-bearing: a neighbor
    must have BEEN through the tail to have second-85% history worth mining."""
    try:
        age = _months_since(cand["created_at"])
        since_push = _months_since(cand["pushed_at"])
    except Exception:
        age = since_push = 0.0
    commits = commit_count(cand["full_name"])
    if commits >= 150 and age >= 10 and since_push <= 3:
        label = "high"
    elif commits >= 50 and age >= 4 and since_push <= 6:
        label = "med"
    else:
        label = "low"
    return {"label": label, "commits": commits, "age_months": round(age, 1), "months_since_push": round(since_push, 1)}


def fan_call(prompt, max_tokens=2000):
    """Thin shim over the shared substrate (mine_common owns the fan plumbing);
    keeps this tool's die-on-failure semantics."""
    txt = mc_fan_call(prompt, max_tokens=max_tokens, timeout_ms=120000)
    if txt is None:
        sys.exit("fan error: call failed")
    return txt


def gh_search(query, limit=12):
    try:
        r = subprocess.run(
            ["gh", "api", "-X", "GET", "search/repositories", "-f", f"q={query}", "-f", "sort=stars",
             "-f", f"per_page={limit}",
             "--jq", ".items[] | {full_name,stargazers_count,description,created_at,pushed_at,language,fork}"],
            capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        print(f"gh search timed out for query: {query[:80]}", file=sys.stderr)
        return []
    out = []
    for line in r.stdout.splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def capability_map():
    return {"tool": "find_neighbors", "version": "0.1",
            "args": '"what you are building" [--json]',
            "what": "intent -> app_type/sub_type + justified mature neighbor repos "
                    "(gh search, maturity measured from commit-count/age)",
            "exit_codes": {"0": "ok", "1": "usage/err"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("intent", nargs="?")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not a.intent:
        if a.json:  # agentic contract: bare --json = self-describing capability map
            print(json.dumps(capability_map())); sys.exit(0)
        print('usage: find_neighbors.py "what you are building" [--json]', file=sys.stderr)
        sys.exit(1)

    # 1) intent -> app_type, sub_type, search queries
    spec = extract_json(fan_call(
        f'A developer is building: "{a.intent}".\n'
        'Output ONLY JSON: {"app_type": "<short label e.g. ai-agent-tool>", '
        '"sub_type": "<more specific e.g. agent-coordination-harness>", '
        '"github_queries": [4-6 GitHub repo-search queries]}.\n'
        'CRITICAL: use GitHub search SYNTAX, not sentences. Each query = 2-4 keywords + qualifiers like '
        '"stars:>150" and "pushed:>2026-01-01". Long natural-language queries return nothing. '
        'Good: "coding agent orchestration stars:>150 pushed:>2026-01-01". '
        'Bad: "a CLI tool that coordinates multiple AI coding agents".'))
    if not spec:
        sys.exit("could not parse intent spec")

    # 2) gh search candidates
    cands = {}
    for q in spec.get("github_queries", []):
        for r in gh_search(q):
            if not r.get("fork"):
                cands[r["full_name"]] = r
    cand_list = list(cands.values())

    listing = "\n".join(
        f"{i+1}. {c['full_name']} ⭐{c['stargazers_count']} [{c.get('language')}] "
        f"created {c['created_at'][:7]} pushed {c['pushed_at'][:7]} — {(c.get('description') or '')[:80]}"
        for i, c in enumerate(cand_list))

    # 3) evaluate / justify
    pick = extract_json(fan_call(
        f'Building: "{a.intent}" (app_type {spec.get("app_type")}, sub_type {spec.get("sub_type")}).\n'
        f"GitHub search returned these candidate repos:\n{listing}\n\n"
        "Pick the ones that are GENUINELY valuable prior-art NEIGHBORS to mine for the second-85% — the hidden "
        "work this project will hit. A good neighbor is: same app sub-type, MATURE (long active history, so it has "
        "BEEN through the tail), real (not star-gamed, not abandoned). REJECT awesome-lists, docs, demos, tutorials, "
        "and star-inflated junk. (Maturity is measured separately from real repo data — do NOT guess it.) "
        "Return ONLY JSON: "
        '{"neighbors":[{"repo":..., "why_valuable":"<1 sentence>"}], '
        '"rejected":[{"repo":...,"reason":"<short>"}]}', max_tokens=2500))
    if not pick:
        sys.exit("could not parse neighbor evaluation")

    # measure maturity from gh data (supersedes any LLM guess); drop neighbors we can't locate
    by_name = {c["full_name"]: c for c in cand_list}
    for n in pick.get("neighbors", []):
        cand = by_name.get(n.get("repo"))
        n["maturity"] = measured_maturity(cand) if cand else {"label": "unknown", "commits": 0}
    pick["neighbors"].sort(key=lambda n: -n["maturity"]["commits"])  # mature (most history) first = best prior art

    out = {"intent": a.intent, "app_type": spec.get("app_type"), "sub_type": spec.get("sub_type"),
           "queries": spec.get("github_queries"), "n_candidates": len(cand_list),
           "neighbors": pick.get("neighbors", []), "rejected": pick.get("rejected", [])}

    if a.json:
        print(json.dumps(out, indent=2)); return
    print(f"intent: {a.intent}")
    print(f"app_type: {out['app_type']} / {out['sub_type']}")
    print(f"searched {len(cand_list)} candidates via {len(out['queries'])} queries\n")
    print("RECOMMENDED NEIGHBORS (most mature first = best prior art):")
    for n in out["neighbors"]:
        m = n.get("maturity", {})
        print(f"  ✓ {n.get('repo')}  [{m.get('label')}: {m.get('commits')} commits, "
              f"{m.get('age_months')}mo old, pushed {m.get('months_since_push')}mo ago]")
        print(f"      ↳ {n.get('why_valuable')}")
    print("\nrejected (sample):")
    for r in out["rejected"][:6]:
        print(f"  ✗ {r.get('repo')} — {r.get('reason')}")


if __name__ == "__main__":
    main()
