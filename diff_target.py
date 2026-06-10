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
import argparse, json, re, subprocess, sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mine_common import fan_call, extract_json, EXIT_OK, EXIT_ERR, EXIT_NOT_FOUND  # shared mine substrate

SRC_EXT = (".py", ".ts", ".rs", ".ex", ".go", ".js")
# words that name the CHANGE rather than the capability — useless as search terms
KEYWORD_STOP = {"fix", "fixes", "fixed", "update", "updates", "updated", "improvement", "improve",
                "support", "supports", "handling", "handle", "management", "manage", "change",
                "changes", "addition", "feature", "features", "issue", "behavior", "enhancement",
                "integration", "general", "misc", "with", "from", "into", "this", "that", "data"}
# evidence candidates: real source/docs/config only — vendored blobs, lockfiles and minified
# bundles match every keyword and buried the true evidence on goose (tokens.json, pnpm-lock.yaml)
EVIDENCE_EXT = SRC_EXT + (".tsx", ".jsx", ".exs", ".java", ".kt", ".swift", ".rb", ".php",
                          ".c", ".cc", ".cpp", ".h", ".sh", ".md", ".toml", ".yaml", ".yml")
EVIDENCE_EXCLUDE = re.compile(r"(^|/)(node_modules|vendor|third_party|dist|build|assets)/"
                              r"|lock\b|\.lock\b|\.min\.|\.snap$|_data/", re.I)


def evidence_candidate(path):
    """Is this file usable as verdict evidence? Pure — testable without a repo."""
    return path.endswith(EVIDENCE_EXT) and not EVIDENCE_EXCLUDE.search(path)


def capability_map():
    return {"tool": "2080-diff-target", "version": "0.3",
            "args": "<target-repo> <checklist.json> [--json] [--yes]",
            "exit_codes": {"0": "ok", "1": "usage/err", "2": "not_found"}}


def category_keywords(cat):
    """Deterministic search terms for a category: domain words from category + aliases,
    minus change-words (fix/update/...) that would match every commit-shaped string."""
    aliases = cat.get("aliases", "")
    if isinstance(aliases, list):
        aliases = " ".join(aliases)
    words = re.findall(r"[a-zA-Z][a-zA-Z_-]{3,}", f"{cat.get('category', '')} {aliases}".lower())
    seen, out = set(), []
    for w in words:
        if w in KEYWORD_STOP or w in seen:
            continue
        seen.add(w); out.append(w)
    return out[:6]


def rank_evidence_files(kw_hits, nfiles, top=6):
    """Rank files by how many distinct category keywords they match. A keyword hitting >40%
    of the repo is too generic to discriminate and is dropped. Pure — testable without git."""
    score = Counter()
    for kw, hits in kw_hits.items():
        if nfiles and len(hits) > 0.4 * nfiles:
            continue
        for f in hits:
            score[f] += 1
    return [f for f, _ in score.most_common(top)]


def build_dir_map(files, top=40):
    """Directory → file-count summary (depth ≤2). The model sees the SHAPE of the repo
    instead of an alphabetical file dump that starts at .github/."""
    c = Counter()
    for f in files:
        d = f.rsplit("/", 1)[0] if "/" in f else "."
        c["/".join(d.split("/")[:2])] += 1
    return "\n".join(f"{d}/ ({n} files)" for d, n in c.most_common(top))


def _grep_files(repo, kw):
    r = subprocess.run(["git", "-C", repo, "grep", "-ilI", "--untracked", "-e", kw],
                       capture_output=True, text=True)
    return kw, set(f for f in r.stdout.split("\n") if f)


def prime_keyword_cache(repo, cats, allowed):
    """One parallel grep pass for every unique keyword across all categories (greps release
    the GIL in subprocesses; serial was 136s on goose, this is the wall-clock fix). Hits are
    pre-filtered to evidence candidates so junk never reaches the ranking."""
    kws = sorted({k for c in cats for k in category_keywords(c)})
    with ThreadPoolExecutor(max_workers=8) as ex:
        return {kw: hits & allowed for kw, hits in ex.map(lambda k: _grep_files(repo, k), kws)}


def category_evidence(repo, cat, nfiles, cache, char_budget):
    """Evidence for ONE category: top keyword-matching files + a few matched lines.
    'NO matching files' is itself load-bearing — a genuine absence signal."""
    kws = category_keywords(cat)
    if not kws:
        return "(no searchable keywords)"
    top = rank_evidence_files({k: cache.get(k, set()) for k in kws}, nfiles)
    if not top:
        return f"keyword search ({', '.join(kws)}): NO matching files anywhere in the repo"
    out = ["files: " + ", ".join(top)]
    r = subprocess.run(["git", "-C", repo, "grep", "-inI", "--untracked"]
                       + [x for k in kws for x in ("-e", k)] + ["--"] + top[:3],
                       capture_output=True, text=True)
    out += [ln[:200] for ln in r.stdout.splitlines()[:6]]
    return "\n".join(out)[:char_budget]


def gather_evidence(repo, cats=None):
    """Scale-aware evidence: full fileset (citation validation), dir map + entry-point excerpts
    (orientation), and per-category keyword-search evidence (the verdict grounding).
    Replaces the old first-80-files-alphabetical + 13KB excerpt, which starved the assessor on
    large repos (measured: 0.083 precision on goose — it judged a .github helper as 'the app')."""
    p = Path(repo)
    readme = ""
    for n in ("README.md", "readme.md", "README"):
        if (p / n).exists():
            readme = (p / n).read_text(errors="ignore")[:2500]; break
    # tracked AND untracked-not-ignored — an uncommitted target still has real source
    files = [f for f in subprocess.run(["git", "-C", repo, "ls-files", "--cached", "--others", "--exclude-standard"],
                                        capture_output=True, text=True).stdout.split("\n") if f]
    in_git = bool(files)
    if not in_git:  # non-git dir: orientation still works; grep evidence is skipped
        files = sorted(str(x.relative_to(p)) for x in p.rglob("*") if x.is_file())[:400]
    # entry-point-ish source first: shallow, not dot-dirs, main/cli/app/server-shaped names
    def src_rank(f):
        return ("/." in f or f.startswith("."), f.count("/"),
                0 if re.search(r"(main|cli|app|server|index|lib)\.", f) else 1, f)
    src = ""
    for f in sorted((f for f in files if f.endswith(SRC_EXT)), key=src_rank)[:6]:
        if len(src) >= 9000:
            break
        try:
            src += f"\n# === {f} ===\n" + (p / f).read_text(errors="ignore")[:2500]
        except Exception:
            pass
    cat_ev = {}
    if cats and in_git:
        allowed = {f for f in files if evidence_candidate(f)}
        cache = prime_keyword_cache(repo, cats, allowed)
        budget = max(350, 26000 // max(1, len(cats)))
        for i, c in enumerate(cats):
            cat_ev[i] = category_evidence(repo, c, len(allowed), cache, budget)
    return {"readme": readme, "files": files, "dir_map": build_dir_map(files),
            "source_excerpt": src[:10000], "category_evidence": cat_ev}


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


def clean_synonym_terms(terms, kws):
    """Sanitize LLM-proposed search terms (pure): strings only, ≥3 chars, deduped, not already
    among the original keywords (re-searching the same words proves nothing), capped at 8."""
    seen, out = set(kws), []
    for t in terms or []:
        if not isinstance(t, str):
            continue
        t = t.strip()
        k = t.lower()
        if len(t) < 3 or k in seen:
            continue
        seen.add(k); out.append(t)
    return out[:8]


def merge_escalation(cats, idx_to_asmt, fileset):
    """Apply re-assessments to escalated gap categories (pure). A flipped verdict keeps the
    audit trail: escalated=True plus the original gap reasoning. Unflipped gaps also get
    escalated=True — 'survived a synonym search' strengthens the verdict."""
    for i, asmt in idx_to_asmt.items():
        c = cats[i]
        c["escalated"] = True
        new = asmt.get("status")
        if new in ("covered", "partial", "na_by_design") and new != c["status"]:
            c["pre_escalation_reasoning"] = c.get("reasoning", "")
            c["status"] = new
            c["reasoning"] = asmt.get("reasoning", "")
            bad = [f for f in (asmt.get("cited_files") or []) if f not in fileset]
            c["citation_unverified"] = bool(bad)
            if new == "partial":
                c["fix_sites"], c["fix_sites_unverified"] = validate_fix_sites(asmt.get("fix_sites"), fileset)
            else:
                c.pop("fix_sites", None); c.pop("fix_sites_unverified", None)
    return cats


def escalate_gaps(target, cl, cats, ev, fileset):
    """Second-opinion pass for GAP verdicts — the measured residual failure mode (precision run:
    gap verdicts 1/4 correct vs partials 22/26; every false gap was vocabulary mismatch, e.g.
    'optional dependency handling' implemented as ensure_peekaboo()).

    The LLM only PROPOSES alternative search terms; evidence still comes from deterministic
    git grep over the filtered fileset. A gap stands only if the synonym search is ALSO dry.
    Cost: ≤2 extra fan calls, and only when gaps exist (they're rare post-evidence-fix)."""
    gaps = [i for i, c in enumerate(cats) if c.get("status") == "gap"]
    if not gaps or not ev["category_evidence"]:
        return cats

    listing = "\n".join(f"{i}: {cats[i]['category']} (aliases: {cats[i].get('aliases', '')})" for i in gaps)
    raw = fan_call(
        f"A repo of app_type {cl.get('app_type')} was judged MISSING these capabilities, but the search "
        "used only the capability names — implementations often live under different vocabulary "
        "(library names, function/symbol names, config keys, CLI tools).\n"
        f"REPO MAP:\n{ev['dir_map'][:1500]}\n\nCAPABILITIES:\n{listing}\n\n"
        "For EACH, propose 5-8 alternative search terms an implementation would actually contain "
        "(concrete identifiers > concepts; match the repo's likely language/stack). "
        'Return ONLY JSON: {"<index>": ["term", ...], ...}', max_tokens=200 * len(gaps) + 500)
    syn = extract_json(raw) if raw else None
    if not syn:
        return cats  # escalation is best-effort; the original verdicts stand

    allowed = {f for f in fileset if evidence_candidate(f)}
    found = {}
    for i in gaps:
        terms = clean_synonym_terms(syn.get(str(i)), category_keywords(cats[i]))
        if not terms:
            cats[i]["escalated"] = True
            continue
        with ThreadPoolExecutor(max_workers=8) as ex:
            hits = {kw: s & allowed for kw, s in ex.map(lambda t: _grep_files(target, t), terms)}
        top = rank_evidence_files(hits, len(allowed))
        if not top:
            cats[i]["escalated"] = True  # synonym search also dry — the gap verdict is now stronger
            continue
        r = subprocess.run(["git", "-C", target, "grep", "-inI", "--untracked"]
                           + [x for t in terms for x in ("-e", t)] + ["--"] + top[:3],
                           capture_output=True, text=True)
        found[i] = ("files: " + ", ".join(top) + "\n"
                    + "\n".join(ln[:200] for ln in r.stdout.splitlines()[:6]))[:1800]
    if not found:
        return cats

    relisting = "\n".join(
        f"{i}. {cats[i]['category']} — day-1 tell: {cats[i].get('day1_tell', '(none)')}\n"
        f"   prior verdict: gap ({cats[i].get('reasoning', '')[:140]})\n   NEW EVIDENCE (synonym search): {ev_}"
        for i, ev_ in found.items())
    raw = fan_call(
        f"TARGET repo '{target}' (app_type {cl.get('app_type')}). These capabilities were judged GAP, but a "
        "follow-up search under implementation vocabulary found the evidence below. Re-judge EACH using ONLY "
        "this evidence: status = covered | partial | gap | na_by_design (keep gap if the evidence does not "
        "actually demonstrate the capability — mentions are not implementations).\n"
        f"{relisting}\n\n"
        "Return ONLY JSON: {\"assessments\":[{\"n\":<index>,\"status\":\"...\",\"reasoning\":\"...\","
        "\"cited_files\":[...],\"fix_sites\":[{\"file\":\"...\",\"what\":\"...\"}]}]}",
        max_tokens=160 * len(found) + 500)
    out = extract_json(raw) if raw else None
    if not out:
        return cats
    idx_to_asmt = {a_["n"]: a_ for a_ in out.get("assessments", []) if a_.get("n") in found}
    return merge_escalation(cats, idx_to_asmt, fileset)


def assess_target(target, cl):
    """Assess a target repo against a checklist dict. Importable core (used by check.py).
    Returns {"sub_type", "app_type", "categories":[{...,"status","reasoning","citation_unverified",
    and on gap/partial: "fix_sites","fix_sites_unverified"}]}. GAP verdicts get a synonym-escalation
    second pass before they're final (see escalate_gaps)."""
    cats = [{**c, "tier": "required"} for c in cl.get("required", [])] + \
           [{**c, "tier": "optional"} for c in cl.get("optional", [])]
    ev = gather_evidence(target, cats)

    cat_listing = "\n".join(
        f"{i+1}. [{c['tier']}] {c['category']} — day-1 tell: {c.get('day1_tell', '(none)')}\n"
        f"   EVIDENCE: {ev['category_evidence'].get(i, '(none gathered)')}"
        for i, c in enumerate(cats))

    fileset = set(ev["files"])
    raw = fan_call(
        f"TARGET repo '{target}' (claimed app_type {cl.get('app_type')}). Evidence:\n"
        f"README:\n{ev['readme']}\n\n"
        f"REPO MAP (directory → file count; the repo's real shape and size):\n{ev['dir_map']}\n\n"
        f"ENTRY-POINT SOURCE EXCERPTS:\n{ev['source_excerpt']}\n\n"
        f"CHECKLIST — categories mature {cl.get('app_type')} repos had to add. Each includes EVIDENCE from a "
        "deterministic keyword search across the ENTIRE repo (top matching files + matched lines). "
        "'NO matching files' is a genuine absence signal; matched files are where the capability most likely "
        f"lives — weigh them over impressions from the README:\n{cat_listing}\n\n"
        "STEP 1: in one short phrase, identify the TARGET's actual sub_type from the evidence.\n"
        "STEP 2: assess EACH category using ONLY the evidence: status = covered | partial | gap | na_by_design. "
        "Mark na_by_design when the category does not apply to THIS target, for either reason:\n"
        "  (a) STRUCTURALLY inapplicable to the sub_type — e.g. multi-agent coordination (handoffs, leadership "
        "leases, peer presence, stale-base) does not apply to a single-process analysis/CLI tool;\n"
        "  (b) DIFFERENT PRODUCT MECHANISM — a capability that belongs to a different kind of engine than the "
        "target's. E.g. for a prior-art / LLM-based completeness tool, line-level code-review suggestions, "
        "static-analysis/AST scanning, multi-language parsers, and dependency/supply-chain scanners are a "
        "DIFFERENT mechanism (a SAST/linter engine), not this tool's job — mark those na_by_design, not gap.\n"
        "For each: reasoning (1 sentence) and cited_files (file paths that APPEAR IN THE EVIDENCE/MAP above; "
        "[] if none; do NOT invent filenames). For each gap or partial ONLY, also give fix_sites: 1-3 of "
        '{"file": a file path FROM THE EVIDENCE where the capability would naturally be added or extended, '
        '"what": one concrete line of what to add there}; [] only when no existing file is a sensible anchor. '
        "Return ONLY JSON: "
        '{"sub_type":"...","assessments":[{"n":<num>,"status":"...","reasoning":"...","cited_files":[...],'
        '"fix_sites":[{"file":"...","what":"..."}]}]}',
        max_tokens=max(4000, len(cats) * 150), timeout_ms=300000)
    if raw is None:  # fan call itself failed (timeout/transport) — not a parse problem
        print("assess_target: LLM call failed (fan returned no result)", file=sys.stderr)
        return None
    out = extract_json(raw)
    if not out:
        Path("/tmp/2080-diff-raw.txt").write_text(raw)
        print("assess_target: unparseable model output — raw saved to /tmp/2080-diff-raw.txt", file=sys.stderr)
        return None

    cats = apply_assessments(cats, out.get("assessments", []), fileset)
    cats = escalate_gaps(target, cl, cats, ev, fileset)
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
        if c.get("escalated"):
            flag += " ↻escalated" if "pre_escalation_reasoning" in c else " ↻gap-survived-synonym-search"
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
