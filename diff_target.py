#!/usr/bin/env python3
"""
diff_target.py — point a domain checklist at a target repo and report coverage.

For each required/optional category in the checklist (with its day-1 tell), assess whether
the TARGET already covers it — covered | partial | gap | na_by_design — grounded in the
target's actual README + file tree + source. Output: the target's second-85% gap list.

Usage: diff_target.py <target-repo> <checklist.json> [--json]
"""
import argparse, json, re, subprocess, sys
from pathlib import Path


def fan_call(prompt, max_tokens=3000, model="gpt-5.5", provider="openai-codex", reasoning="low"):
    cfg = {"calls": [{"id": "0", "provider": provider, "model": model, "reasoning": reasoning,
                      "prompt": prompt, "maxTokens": max_tokens, "timeoutMs": 180000}]}
    r = subprocess.run(["fan"], input=json.dumps(cfg), capture_output=True, text=True, timeout=300)
    if not r.stdout:
        sys.exit(f"fan failed: {r.stderr[:300]}")
    res = json.loads(r.stdout)["results"][0]
    if not res.get("ok"):
        sys.exit(f"fan error: {res.get('error')}")
    return res["text"]


def extract_json(t):
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"[\{\[][\s\S]*[\}\]]", t)
        return json.loads(m.group(0)) if m else None


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("checklist")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    cl = json.loads(Path(a.checklist).read_text())
    cats = [{**c, "tier": "required"} for c in cl.get("required", [])] + \
           [{**c, "tier": "optional"} for c in cl.get("optional", [])]
    ev = gather_evidence(a.target)

    cat_listing = "\n".join(
        f"{i+1}. [{c['tier']}] {c['category']} — day-1 tell: {c.get('day1_tell', '(none)')}"
        for i, c in enumerate(cats))

    fileset = set(ev["files"])
    out = extract_json(fan_call(
        f"TARGET repo '{a.target}' (claimed app_type {cl.get('app_type')}). Evidence:\n"
        f"README:\n{ev['readme']}\n\n"
        f"FILES — these are the ONLY files that exist; never cite a file outside this list:\n{json.dumps(ev['files'])}\n\n"
        f"SOURCE:\n{ev['source_excerpt']}\n\n"
        f"CHECKLIST — categories mature {cl.get('app_type')} repos had to add, each with a day-1 check:\n{cat_listing}\n\n"
        "STEP 1: in one short phrase, identify the TARGET's actual sub_type from the evidence.\n"
        "STEP 2: assess EACH category using ONLY the evidence: status = covered | partial | gap | na_by_design. "
        "Mark na_by_design ONLY when the category is STRUCTURALLY inapplicable to that sub_type — e.g. multi-agent "
        "coordination categories (handoffs, leadership leases, peer presence, stale-base) do NOT apply to a "
        "single-process analysis/CLI tool. For each: reasoning (1 sentence) and cited_files (files FROM THE LIST you "
        "based it on; [] if none; do NOT invent filenames). Return ONLY JSON: "
        '{"sub_type":"...","assessments":[{"n":<num>,"status":"...","reasoning":"...","cited_files":[...]}]}',
        max_tokens=max(3500, len(cats) * 110)))
    if not out:
        sys.exit("could not parse assessment")

    sub_type = out.get("sub_type", "?")
    by_n = {a_["n"]: a_ for a_ in out.get("assessments", [])}
    for i, c in enumerate(cats):
        asmt = by_n.get(i + 1, {})
        c["status"] = asmt.get("status", "unknown")
        c["reasoning"] = asmt.get("reasoning", "")
        bad = [f for f in (asmt.get("cited_files") or []) if f not in fileset]  # deterministic anti-hallucination
        c["citation_unverified"] = bool(bad)

    if a.json:
        print(json.dumps({"target": a.target, "app_type": cl.get("app_type"), "categories": cats}, indent=2)); return

    order = {"gap": 0, "partial": 1, "covered": 2, "na_by_design": 3, "unknown": 4}
    icon = {"gap": "❌", "partial": "🟡", "covered": "✅", "na_by_design": "⚪", "unknown": "❔"}
    print(f"=== {a.target} vs {cl.get('app_type')} checklist ===")
    print(f"target sub_type (inferred): {sub_type}\n")
    req_gaps = [c for c in cats if c["tier"] == "required" and c["status"] in ("gap", "partial")]
    print(f"REQUIRED GAPS (the actionable second-85% — {len(req_gaps)} of {sum(1 for c in cats if c['tier']=='required')} required):")
    for c in sorted([c for c in cats if c["tier"] == "required"], key=lambda x: order.get(x["status"], 9)):
        flag = " ⚠unverified-citation" if c.get("citation_unverified") else ""
        print(f"  {icon.get(c['status'],'?')} {c['status']:13} {c['category']}{flag}")
        if c["status"] in ("gap", "partial"):
            print(f"        ↳ {c['reasoning'][:140]}")
    print(f"\nOPTIONAL (project-specific) — {sum(1 for c in cats if c['tier']=='optional' and c['status'] in ('gap','partial'))} gaps "
          f"(shown only if gap/partial):")
    for c in [c for c in cats if c["tier"] == "optional" and c["status"] in ("gap", "partial")]:
        print(f"  {icon.get(c['status'],'?')} {c['category']}")


main()
