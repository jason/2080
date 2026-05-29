#!/usr/bin/env python3
"""
check.py — 2080's KEYSTONE gate. `2080 check`: is this target's second-85% closed enough to ship?

One command unifies three capabilities the feature-spine dogfood flagged as 2080's own gaps,
each by exposing a primitive 2080 already has:

  CUSTOM RULES  ← the spine/checklist (--spine) IS the rule set; lenses (cluster_fixes / feature_mine)
                  define what those rules are. Point check at any checklist.
  QUALITY GATE  ← runs diff_target's assessment, then BLOCKS (exit 3) when required-tier gaps remain
                  above --threshold. The blocking logic is lens-agnostic.
  REPORTING     ← human gap report + --json verdict over the same assessment.
  CI/CD         ← the exit code IS the integration: `2080 check . --spine X` in a CI step fails the
                  build when the second-85% isn't closed. (No workflow ships yet — this makes 2080
                  CI-READY, which is not the same as having CI.)

na_by_design categories never block (a SAST feature isn't this tool's job). Only genuinely-applicable
required gaps count.

Usage:
  check.py <target-repo> --spine <checklist.json> [--threshold N] [--fail-on gap|partial]
           [--json] [--yes]
Exit codes: 0 PASS (gate open) | 1 USAGE/ERR | 2 NOT_FOUND | 3 GATED (required gaps remain)
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

from mine_common import EXIT_OK, EXIT_ERR, EXIT_NOT_FOUND
from diff_target import assess_target

EXIT_GATED = 3  # mirrors rally-flow's gate() exit code: completion refused


def capability_map():
    return {"tool": "2080-check", "version": "0.1",
            "args": "<target-repo> --spine <checklist.json> [--threshold N] [--fail-on gap|partial] [--json] [--yes]",
            "fail_on": ["gap", "partial"],
            "exit_codes": {"0": "pass (gate open)", "1": "usage/err", "2": "not_found", "3": "gated (required gaps remain)"}}


def evaluate(result, fail_on):
    """Split assessed categories into blocking (applicable required gaps) vs the rest.
    Blocking = tier==required AND status in fail_on AND not na_by_design/covered."""
    block_statuses = {"gap", "partial"} if fail_on == "partial" else {"gap"}
    blocking, required_total = [], 0
    for c in result["categories"]:
        if c.get("tier") != "required":
            continue
        required_total += 1
        if c.get("status") in block_statuses:
            blocking.append({"category": c["category"], "status": c["status"],
                             "reasoning": c.get("reasoning", ""),
                             "day1_tell": c.get("day1_tell", ""),
                             "citation_unverified": bool(c.get("citation_unverified"))})
    return blocking, required_total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?")
    ap.add_argument("--spine", "--checklist", dest="spine", help="checklist/feature-spine JSON")
    ap.add_argument("--threshold", type=int, default=0, help="max applicable required gaps allowed before the gate blocks")
    ap.add_argument("--fail-on", choices=["gap", "partial"], default="partial",
                    help="'gap' blocks only on full gaps; 'partial' (default) also blocks on partials")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--yes", "-y", action="store_true", help="accepted for agentic use; check is read-only")
    a = ap.parse_args()

    if not a.target:
        if a.json:
            print(json.dumps(capability_map())); sys.exit(EXIT_OK)
        print(capability_map()["args"], file=sys.stderr); sys.exit(EXIT_ERR)
    if not a.spine:
        print("--spine <checklist.json> is required", file=sys.stderr); sys.exit(EXIT_ERR)

    spine_path = Path(a.spine)
    if not spine_path.exists():
        print(f"spine not found: {a.spine}", file=sys.stderr); sys.exit(EXIT_NOT_FOUND)
    if not Path(a.target).exists():
        print(f"target not found: {a.target}", file=sys.stderr); sys.exit(EXIT_NOT_FOUND)

    cl = json.loads(spine_path.read_text())
    result = assess_target(a.target, cl)
    if not result:
        print("assessment failed (could not parse model output)", file=sys.stderr); sys.exit(EXIT_ERR)

    blocking, required_total = evaluate(result, a.fail_on)
    over = max(0, len(blocking) - a.threshold)
    gated = over > 0
    verdict = {
        "ok": not gated,
        "gated": gated,
        "target": a.target,
        "spine": str(spine_path),
        "app_type": cl.get("app_type"),
        "sub_type": result["sub_type"],
        "required_total": required_total,
        "blocking_count": len(blocking),
        "threshold": a.threshold,
        "fail_on": a.fail_on,
        "blocking_gaps": blocking,
    }

    if a.json:
        print(json.dumps(verdict, indent=2))
        sys.exit(EXIT_GATED if gated else EXIT_OK)

    head = "🚫 GATED" if gated else "✅ PASS"
    print(f"{head} — {a.target} vs {cl.get('app_type')} spine ({spine_path.name})")
    print(f"sub_type: {result['sub_type']}")
    print(f"required: {required_total} | blocking (applicable required {a.fail_on}s): {len(blocking)} "
          f"| threshold: {a.threshold}\n")
    if blocking:
        print("BLOCKING GAPS (close these to open the gate):")
        for g in blocking:
            flag = " ⚠unverified-citation" if g["citation_unverified"] else ""
            icon = "❌" if g["status"] == "gap" else "🟡"
            print(f"  {icon} {g['status']:8} {g['category']}{flag}")
            if g["reasoning"]:
                print(f"        ↳ {g['reasoning'][:140]}")
            if g["day1_tell"]:
                print(f"        check: {g['day1_tell'][:120]}")
    else:
        print("No applicable required gaps remain — the second-85% is closed for this spine.")
    sys.exit(EXIT_GATED if gated else EXIT_OK)


if __name__ == "__main__":
    main()
