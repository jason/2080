#!/usr/bin/env python3
"""
diff_target.py — point a domain checklist at a target repo and report coverage.

For each required/optional category in the checklist (with its day-1 tell), assess whether
the TARGET already covers it — covered | partial | gap | na_by_design — grounded in the
target's actual README + file tree + source. Output: the target's second-85% gap list.

Every gap/partial verdict additionally carries fix_sites — concrete (file, what-to-add) anchors
chosen FROM the target's real fileset — so a fixing agent knows WHERE to act, not just what
category is missing. Same deterministic anti-hallucination as cited_files: a fix_site pointing
at a file that doesn't exist is dropped and the category flagged fix_sites_unverified.

Usage: diff_target.py <target-repo> <checklist.json> [--json] [--yes]
Exit codes: 0 OK | 1 usage/err | 2 not_found
"""
import argparse, json, subprocess, sys
from pathlib import Path

from mine_common import fan_call, extract_json, EXIT_OK, EXIT_ERR, EXIT_NOT_FOUND  # shared mine substrate


def capability_map():
    return {"tool": "2080-diff-target", "version": "0.2",
            "args": "<target-repo> <checklist.json> [--json] [--yes]",
            "exit_codes": {"0": "ok", "1": "usage/err", "2": "not_found"}}


def gather_evidence(repo):
    p = Path(repo)
    readme = ""
    for n in ("README.md", "readme.md", "README"):
        if (p / n).exists():
            readme = (p / n).read_text(errors="ignore")[:2500]; break
    # tracked AND untracked-not-ignored — an uncommitted target still has real source
    files = [f for f in subprocess.run(["git", "-C", repo, "ls-files", "--cached", "--others", "--exclude-standard"],
                                        capture_output=True, text=True).stdout.split("\n") if f][:80]
    src = ""
    for f in files:
        if f.endswith((".py", ".ts", ".rs", ".ex", ".go", ".js")) and len(src) < 13000:
            try:
                src += f"\n# === {f} ===\n" + (p / f).read_text(errors="ignore")[:4500]
            except Exception:
                pass
    return {"readme": readme, "files": files, "source_excerpt": src[:15000]}


def validate_fix_sites(sites, fileset):
    """Deterministic anti-hallucination for fix_sites (same pattern as cited_files): keep only
    sites whose file exists in the real fileset. Returns (kept_sites, any_dropped)."""
    kept, dropped = [], False
    for s in sites or []:
        f = s.get("file") if isinstance(s, dict) else None
        if f in fileset:
            kept.append({"file": f, "what": str(s.get("what", ""))})
        else:
            dropped = True
    return kept, dropped


def apply_assessments(cats, assessments, fileset):
    """Merge LLM assessments into the checklist categories (pure; LLM-free, hence testable).
    Attaches status/reasoning/citation_unverified to every category, and fix_sites (validated,
    possibly []) + fix_sites_unverified to every gap/partial so downstream consumers can rely
    on the keys existing."""
    by_n = {a_.get("n"): a_ for a_ in assessments}
    for i, c in enumerate(cats):
        asmt = by_n.get(i + 1, {})
        c["status"] = asmt.get("status", "unknown")
        c["reasoning"] = asmt.get("reasoning", "")
        bad = [f for f in (asmt.get("cited_files") or []) if f not in fileset]  # deterministic anti-hallucination
        c["citation_unverified"] = bool(bad)
        if c["status"] in ("gap", "partial"):
            c["fix_sites"], c["fix_sites_unverified"] = validate_fix_sites(asmt.get("fix_sites"), fileset)
    return cats


def assess_target(target, cl):
    """Assess a target repo against a checklist dict. Importable core (used by check.py).
    Returns {"sub_type", "app_type", "categories":[{...,"status","reasoning","citation_unverified",
    and on gap/partial: "fix_sites","fix_sites_unverified"}]}."""
    cats = [{**c, "tier": "required"} for c in cl.get("required", [])] + \
           [{**c, "tier": "optional"} for c in cl.get("optional", [])]
    ev = gather_evidence(target)

    cat_listing = "\n".join(
        f"{i+1}. [{c['tier']}] {c['category']} — day-1 tell: {c.get('day1_tell', '(none)')}"
        for i, c in enumerate(cats))

    fileset = set(ev["files"])
    out = extract_json(fan_call(
        f"TARGET repo '{target}' (claimed app_type {cl.get('app_type')}). Evidence:\n"
        f"README:\n{ev['readme']}\n\n"
        f"FILES — these are the ONLY files that exist; never cite a file outside this list:\n{json.dumps(ev['files'])}\n\n"
        f"SOURCE:\n{ev['source_excerpt']}\n\n"
        f"CHECKLIST — categories mature {cl.get('app_type')} repos had to add, each with a day-1 check:\n{cat_listing}\n\n"
        "STEP 1: in one short phrase, identify the TARGET's actual sub_type from the evidence.\n"
        "STEP 2: assess EACH category using ONLY the evidence: status = covered | partial | gap | na_by_design. "
        "Mark na_by_design when the category does not apply to THIS target, for either reason:\n"
        "  (a) STRUCTURALLY inapplicable to the sub_type — e.g. multi-agent coordination (handoffs, leadership "
        "leases, peer presence, stale-base) does not apply to a single-process analysis/CLI tool;\n"
        "  (b) DIFFERENT PRODUCT MECHANISM — a capability that belongs to a different kind of engine than the "
        "target's. E.g. for a prior-art / LLM-based completeness tool, line-level code-review suggestions, "
        "static-analysis/AST scanning, multi-language parsers, and dependency/supply-chain scanners are a "
        "DIFFERENT mechanism (a SAST/linter engine), not this tool's job — mark those na_by_design, not gap.\n"
        "For each: reasoning (1 sentence) and cited_files (files FROM THE LIST you based it on; [] if none; do NOT "
        "invent filenames). For each gap or partial ONLY, also give fix_sites: 1-3 of "
        '{"file": a file FROM THE LIST where the capability would naturally be added or extended, '
        '"what": one concrete line of what to add there}; [] only when no existing file is a sensible anchor. '
        "Return ONLY JSON: "
        '{"sub_type":"...","assessments":[{"n":<num>,"status":"...","reasoning":"...","cited_files":[...],'
        '"fix_sites":[{"file":"...","what":"..."}]}]}',
        max_tokens=max(4000, len(cats) * 150)))
    if not out:
        return None

    cats = apply_assessments(cats, out.get("assessments", []), fileset)
    return {"sub_type": out.get("sub_type", "?"), "app_type": cl.get("app_type"), "categories": cats}


def print_fix_sites(c):
    for s in c.get("fix_sites") or []:
        print(f"        fix @ {s['file']}: {s['what'][:120]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?")
    ap.add_argument("checklist", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--yes", "-y", action="store_true", help="accepted for agentic use; diff is read-only")
    a = ap.parse_args()

    def err(msg, code):
        if a.json:
            print(json.dumps({"ok": False, "error": msg, "exit_code": code}), file=sys.stderr)
        else:
            print(msg, file=sys.stderr)
        sys.exit(code)

    if not a.target or not a.checklist:
        if a.json and not a.target:
            print(json.dumps(capability_map())); sys.exit(EXIT_OK)
        err(capability_map()["args"], EXIT_ERR)
    if not Path(a.target).exists():
        err(f"target not found: {a.target}", EXIT_NOT_FOUND)
    if not Path(a.checklist).exists():
        err(f"checklist not found: {a.checklist}", EXIT_NOT_FOUND)

    cl = json.loads(Path(a.checklist).read_text())
    result = assess_target(a.target, cl)
    if not result:
        err("assessment failed (could not parse model output)", EXIT_ERR)
    sub_type = result["sub_type"]
    cats = result["categories"]

    if a.json:
        print(json.dumps({"target": a.target, "app_type": cl.get("app_type"), "sub_type": sub_type,
                          "categories": cats}, indent=2)); return

    order = {"gap": 0, "partial": 1, "covered": 2, "na_by_design": 3, "unknown": 4}
    icon = {"gap": "❌", "partial": "🟡", "covered": "✅", "na_by_design": "⚪", "unknown": "❔"}
    print(f"=== {a.target} vs {cl.get('app_type')} checklist ===")
    print(f"target sub_type (inferred): {sub_type}\n")
    req_gaps = [c for c in cats if c["tier"] == "required" and c["status"] in ("gap", "partial")]
    print(f"REQUIRED GAPS (the actionable second-85% — {len(req_gaps)} of {sum(1 for c in cats if c['tier']=='required')} required):")
    for c in sorted([c for c in cats if c["tier"] == "required"], key=lambda x: order.get(x["status"], 9)):
        flag = " ⚠unverified-citation" if c.get("citation_unverified") else ""
        if c.get("fix_sites_unverified"):
            flag += " ⚠unverified-fix-sites"
        print(f"  {icon.get(c['status'],'?')} {c['status']:13} {c['category']}{flag}")
        if c["status"] in ("gap", "partial"):
            print(f"        ↳ {c['reasoning'][:140]}")
            print_fix_sites(c)
    print(f"\nOPTIONAL (project-specific) — {sum(1 for c in cats if c['tier']=='optional' and c['status'] in ('gap','partial'))} gaps "
          f"(shown only if gap/partial):")
    for c in [c for c in cats if c["tier"] == "optional" and c["status"] in ("gap", "partial")]:
        print(f"  {icon.get(c['status'],'?')} {c['category']}")
        print_fix_sites(c)


if __name__ == "__main__":
    main()
