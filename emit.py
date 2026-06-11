#!/usr/bin/env python3
"""
emit.py — turn check.py's gate verdict into a day-1 agent work queue.

WHY: check.py ends at a verdict — a report that says GATED and lists blocking gaps. A report
still needs a human to translate it into work. emit.py is that translation, mechanized: each
blocking gap becomes one task SPEC an implementing agent can consume directly. The task's
acceptance criterion is the gap's day-1 tell VERBATIM (the tell is the measurable "you'd hit
this on day 1" check the spine mined — closing the gap means making the tell pass), and every
task carries a verify_cmd that re-runs the gate, so closure is measured, not claimed. This
converts 2080 from a gap-analysis report into a work queue.

Input modes:
  emit.py --verdict verdict.json            # a saved `check.py ... --json` verdict ('-' = stdin)
  check.py . --spine s.json --json | emit.py            # pipe: stdin is the verdict
  emit.py --target <repo> --spine <checklist.json>      # run the assessment live (one fan call,
                                                        # ~cents/~1-2 min; reuses check/diff_target)

Output: a stable, versioned task-list document —
  {tool:"2080-emit", version, target, spine, generated_from:"verdict"|"live", task_count, tasks}
  task = {id, title, category, tier, status, acceptance, reasoning, evidence, verify_cmd}
Unknown per-gap keys (e.g. fix_sites, cited_files) pass through into task.evidence — the gap
schema grows over time and emit must not drop repair guidance it doesn't recognize.

Formats: --format json | md (md = human/agent-readable backlog, one section per task with an
acceptance checklist). --json forces the json format and one JSON document on stdout.
Exit codes: 0 ok (including an empty queue — gate already open) | 1 usage/err | 2 not_found
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

from mine_common import EXIT_OK, EXIT_ERR, EXIT_NOT_FOUND

VERSION = "0.1"
# Keys emit understands and maps to first-class task fields; everything else is evidence.
KNOWN_GAP_KEYS = {"category", "status", "reasoning", "day1_tell", "tier", "citation_unverified"}


def capability_map():
    return {"tool": "2080-emit", "version": VERSION,
            "args": "[--verdict <verdict.json>|-] | [--target <repo> --spine <checklist.json>] "
                    "[--fail-on gap|partial] [--format json|md] [--json] [--yes]",
            "formats": ["json", "md"],
            "exit_codes": {"0": "ok (task list emitted; may be empty — gate open)",
                           "1": "usage/err", "2": "not_found"}}


def slug(text):
    """Stable task id from a category name: lowercase, runs of non-alnum -> '-'."""
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "uncategorized"


def gap_to_task(gap, target, spine):
    """One blocking gap -> one task spec. acceptance = day1_tell verbatim (it IS the criterion)."""
    cat = gap.get("category", "uncategorized")
    status = gap.get("status", "gap")
    evidence = {"citation_unverified": bool(gap.get("citation_unverified"))}
    evidence.update({k: v for k, v in gap.items() if k not in KNOWN_GAP_KEYS})  # defensive passthrough
    return {"id": slug(cat),
            "title": ("Close gap: " if status == "gap" else "Complete partial: ") + cat,
            "category": cat,
            "tier": gap.get("tier", "required"),  # check.py blocks only on required-tier gaps
            "status": status,
            "acceptance": gap.get("day1_tell", ""),
            "reasoning": gap.get("reasoning", ""),
            "evidence": evidence,
            "verify_cmd": f"check.py {target} --spine {spine} --json"}


def build_doc(verdict, generated_from):
    target, spine = verdict.get("target", "?"), verdict.get("spine", "?")
    tasks = [gap_to_task(g, target, spine) for g in verdict.get("blocking_gaps", [])]
    seen = {}
    for t in tasks:  # stable de-dup: identical categories get -2, -3 suffixes in input order
        n = seen.get(t["id"], 0) + 1
        seen[t["id"]] = n
        if n > 1:
            t["id"] = f"{t['id']}-{n}"
    return {"tool": "2080-emit", "version": VERSION, "target": target, "spine": spine,
            "generated_from": generated_from, "task_count": len(tasks), "tasks": tasks}


def render_md(doc):
    lines = [f"# 2080 work queue — {doc['target']} vs {Path(str(doc['spine'])).name}",
             "",
             f"{doc['task_count']} task(s), generated from {doc['generated_from']}. "
             "Each task is a spec; its acceptance is the spine's day-1 tell. "
             "Run the verify command after each task — closure is measured, not claimed.", ""]
    if not doc["tasks"]:
        lines.append("_No blocking gaps — the gate is already open. Empty queue._")
    for t in doc["tasks"]:
        lines += [f"## {t['id']} — {t['title']}", "",
                  f"- tier: {t['tier']} | status: {t['status']}"]
        if t["reasoning"]:
            lines.append(f"- why it's open: {t['reasoning']}")
        if t["evidence"].get("citation_unverified"):
            lines.append("- ⚠ evidence cites files the assessor could not verify — re-ground before trusting")
        extra = {k: v for k, v in t["evidence"].items() if k != "citation_unverified"}
        if extra:
            lines.append(f"- evidence: `{json.dumps(extra)}`")
        lines += ["", "**Acceptance**", "", f"- [ ] {t['acceptance'] or '(no day-1 tell recorded — define one first)'}",
                  "", f"Verify: `{t['verify_cmd']}`", ""]
    return "\n".join(lines)


def die(msg, code, json_mode):
    if json_mode:
        print(json.dumps({"ok": False, "error": msg, "exit_code": code}), file=sys.stderr)
    else:
        print(msg, file=sys.stderr)
    sys.exit(code)


def load_verdict(a, stdin_text=None):
    """Resolve the input mode -> (verdict_dict, generated_from)."""
    if a.verdict and a.verdict != "-":
        p = Path(a.verdict)
        if not p.exists():
            die(f"verdict not found: {a.verdict}", EXIT_NOT_FOUND, a.json)
        text = p.read_text()
    elif a.verdict == "-" or (not a.target and stdin_text is not None):
        text = sys.stdin.read() if stdin_text is None else stdin_text
    elif a.target:
        if not a.spine:
            die("--spine <checklist.json> is required with --target", EXIT_ERR, a.json)
        spine_path = Path(a.spine)
        if not spine_path.exists():
            die(f"spine not found: {a.spine}", EXIT_NOT_FOUND, a.json)
        if not Path(a.target).exists():
            die(f"target not found: {a.target}", EXIT_NOT_FOUND, a.json)
        from check import evaluate            # reuse the gate's blocking logic, don't duplicate
        from diff_target import assess_target  # reuse the assessor (one fan call)
        cl = json.loads(spine_path.read_text())
        result = assess_target(a.target, cl)
        if not result:
            die("assessment failed (could not parse model output)", EXIT_ERR, a.json)
        axis = result.get("axis") or cl.get("axis")
        blocking, advisory, required_total = evaluate(result, a.fail_on, axis=axis)
        return {"target": a.target, "spine": str(spine_path), "app_type": cl.get("app_type"),
                "sub_type": result["sub_type"], "axis": axis, "required_total": required_total,
                "blocking_count": len(blocking), "advisory_count": len(advisory),
                "fail_on": a.fail_on, "blocking_gaps": blocking, "advisory_gaps": advisory}, "live"
    else:
        die("no input: pass --verdict <file|->, pipe a verdict on stdin, or --target + --spine",
            EXIT_ERR, a.json)
    try:
        verdict = json.loads(text)
    except Exception as e:
        die(f"input is not valid JSON: {e}", EXIT_ERR, a.json)
    if not isinstance(verdict, dict) or "blocking_gaps" not in verdict:
        die("input is not a check.py verdict (missing 'blocking_gaps')", EXIT_ERR, a.json)
    return verdict, "verdict"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdict", help="saved check.py --json verdict file, or '-' for stdin")
    ap.add_argument("--target", help="live mode: target repo (requires --spine; one fan call)")
    ap.add_argument("--spine", "--checklist", dest="spine", help="live mode: checklist/spine JSON")
    ap.add_argument("--fail-on", choices=["gap", "partial"], default="partial",
                    help="live mode: which statuses block (mirrors check.py; default partial)")
    ap.add_argument("--format", choices=["json", "md"], help="output format (default: md; json in --json mode)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--yes", "-y", action="store_true", help="accepted for agentic use; emit is read-only")
    a = ap.parse_args()

    # Agents call via subprocess where stdin is a pipe, never a tty: blank stdin == no input,
    # so bare `emit.py --json` still serves the capability map unattended.
    stdin_text = None
    if not a.verdict and not a.target and not sys.stdin.isatty():
        stdin_text = sys.stdin.read()
    if not a.verdict and not a.target and not (stdin_text or "").strip():
        if a.json:
            print(json.dumps(capability_map())); sys.exit(EXIT_OK)
        print(capability_map()["args"], file=sys.stderr); sys.exit(EXIT_ERR)

    verdict, generated_from = load_verdict(a, stdin_text)
    doc = build_doc(verdict, generated_from)
    fmt = "json" if a.json else (a.format or "md")
    print(json.dumps(doc, indent=2) if fmt == "json" else render_md(doc))
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
