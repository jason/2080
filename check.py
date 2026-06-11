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
                  build when the second-85% isn't closed. The assessment is SPLITTABLE from the gate:
                  --save-assessment persists the (LLM, ~cents, ~1-2 min) assess_target result; later
                  --from-assessment re-gates on it deterministically — fast, free, CI/hook-safe.
                  hooks/stop_gate.sh and .github/workflows/2080-gate.yml ride that path.

na_by_design categories never block (a SAST feature isn't this tool's job). Only genuinely-applicable
required gaps count.

Usage:
  check.py <target-repo> --spine <checklist.json> [--threshold N] [--fail-on gap|partial]
           [--save-assessment FILE] [--from-assessment FILE] [--json] [--yes]
Exit codes: 0 PASS (gate open) | 1 USAGE/ERR | 2 NOT_FOUND | 3 GATED (required gaps remain)
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

from mine_common import EXIT_OK, EXIT_ERR, EXIT_NOT_FOUND
from diff_target import assess_target

EXIT_GATED = 3  # mirrors rally-flow's gate() exit code: completion refused


def capability_map():
    return {"tool": "2080-check", "version": "0.2",
            "args": "<target-repo> --spine <checklist.json> [--threshold N] [--fail-on gap|partial] "
                    "[--save-assessment FILE] [--from-assessment FILE] [--json] [--yes]",
            "fail_on": ["gap", "partial"],
            "robustness_axis": "mined categories are advisory by default (only the generic-baseline "
                               "floor gates); --enforce-mined-robustness restores full gating",
            "assessment": {"--save-assessment": "after the live LLM assess, write the raw assessment JSON to FILE",
                           "--from-assessment": "skip the LLM: load a saved assessment and gate on it (deterministic)"},
            "exit_codes": {"0": "pass (gate open)", "1": "usage/err", "2": "not_found", "3": "gated (required gaps remain)"}}


def die(msg, code, as_json):
    """Errors go to stderr; structured {ok:false,...} when --json so agents never parse prose."""
    print(json.dumps({"ok": False, "error": msg, "exit_code": code}) if as_json else msg, file=sys.stderr)
    sys.exit(code)


def evaluate(result, fail_on, axis=None, enforce_mined_robustness=False):
    """Split assessed categories into blocking (applicable required gaps), advisory, and the rest.
    Blocking = tier==required AND status in fail_on AND not na_by_design/covered.

    ROBUSTNESS axis: mined categories are ADVISORY, only the generic-baseline floor gates.
    Measured (2026-06, ×3 with variance): a hand-written generic checklist out-recalls the mined
    robustness spine (lift −0.15) and mined labels are change-shaped ("dependency fix"), not
    capability-shaped — gating on them is noise (97/117 false-ish blocks on the first external
    target). SCOPE-axis spines, where mining wins (+0.27), gate in full."""
    block_statuses = {"gap", "partial"} if fail_on == "partial" else {"gap"}
    demote_mined = (axis or "").upper() == "ROBUSTNESS" and not enforce_mined_robustness
    blocking, advisory, required_total = [], [], 0
    for c in result["categories"]:
        if c.get("tier") != "required":
            continue
        required_total += 1
        if c.get("status") in block_statuses:
            entry = {"category": c["category"], "status": c["status"],
                     "reasoning": c.get("reasoning", ""),
                     "day1_tell": c.get("day1_tell", ""),
                     "citation_unverified": bool(c.get("citation_unverified"))}
            if c.get("fix_sites"):  # defensive: only some assessments carry fix-site suggestions
                entry["fix_sites"] = c["fix_sites"]
            if demote_mined and c.get("origin") != "generic-baseline":
                advisory.append(entry)
            else:
                blocking.append(entry)
    return blocking, advisory, required_total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?")
    ap.add_argument("--spine", "--checklist", dest="spine", help="checklist/feature-spine JSON")
    ap.add_argument("--threshold", type=int, default=0, help="max applicable required gaps allowed before the gate blocks")
    ap.add_argument("--fail-on", choices=["gap", "partial"], default="partial",
                    help="'gap' blocks only on full gaps; 'partial' (default) also blocks on partials")
    ap.add_argument("--enforce-mined-robustness", action="store_true",
                    help="gate on mined robustness categories too (default: in robustness spines only "
                         "the generic-baseline floor gates; mined categories are advisory)")
    ap.add_argument("--save-assessment", metavar="FILE",
                    help="after the live assess, write the raw assessment JSON to FILE (re-gate later without an LLM)")
    ap.add_argument("--from-assessment", metavar="FILE",
                    help="skip assess_target/LLM: load a saved assessment and run the same gate (deterministic, CI/hook-safe)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--yes", "-y", action="store_true", help="accepted for agentic use; check is read-only")
    a = ap.parse_args()

    if not a.target:
        if a.json:
            print(json.dumps(capability_map())); sys.exit(EXIT_OK)
        print(capability_map()["args"], file=sys.stderr); sys.exit(EXIT_ERR)
    if not a.spine:
        die("--spine <checklist.json> is required", EXIT_ERR, a.json)

    spine_path = Path(a.spine)
    if not spine_path.exists():
        die(f"spine not found: {a.spine}", EXIT_NOT_FOUND, a.json)
    if not Path(a.target).exists():
        die(f"target not found: {a.target}", EXIT_NOT_FOUND, a.json)

    cl = json.loads(spine_path.read_text())
    if a.from_assessment:
        asmt_path = Path(a.from_assessment)
        if not asmt_path.exists():
            die(f"assessment not found: {a.from_assessment} (generate with --save-assessment)", EXIT_NOT_FOUND, a.json)
        try:
            result = json.loads(asmt_path.read_text())
        except Exception as e:
            die(f"assessment unreadable: {a.from_assessment}: {e}", EXIT_ERR, a.json)
        if not isinstance(result, dict) or not isinstance(result.get("categories"), list):
            die(f"invalid assessment (no 'categories' list): {a.from_assessment}", EXIT_ERR, a.json)
    else:
        result = assess_target(a.target, cl)
        if not result:
            die("assessment failed (could not parse model output)", EXIT_ERR, a.json)
        if a.save_assessment:
            Path(a.save_assessment).write_text(json.dumps(result, indent=2) + "\n")

    axis = result.get("axis") or cl.get("axis")  # old saved assessments lack axis; the spine has it
    blocking, advisory, required_total = evaluate(result, a.fail_on, axis=axis,
                                                  enforce_mined_robustness=a.enforce_mined_robustness)
    over = max(0, len(blocking) - a.threshold)
    gated = over > 0
    verdict = {
        "ok": not gated,
        "gated": gated,
        "target": a.target,
        "spine": str(spine_path),
        "app_type": cl.get("app_type"),
        "sub_type": result.get("sub_type", "?"),
        "axis": axis,
        "required_total": required_total,
        "blocking_count": len(blocking),
        "advisory_count": len(advisory),
        "threshold": a.threshold,
        "fail_on": a.fail_on,
        "blocking_gaps": blocking,
        "advisory_gaps": advisory,
    }

    if a.json:
        print(json.dumps(verdict, indent=2))
        sys.exit(EXIT_GATED if gated else EXIT_OK)

    head = "🚫 GATED" if gated else "✅ PASS"
    print(f"{head} — {a.target} vs {cl.get('app_type')} spine ({spine_path.name})")
    print(f"sub_type: {result.get('sub_type', '?')}")
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
            if g.get("fix_sites"):
                for s in g["fix_sites"][:3]:
                    if isinstance(s, dict):
                        print(f"        fix @ {s.get('file', '?')}: {str(s.get('what', ''))[:110]}")
                    else:
                        print(f"        fix @ {str(s)[:120]}")
    else:
        print("No applicable required gaps remain — the second-85% is closed for this spine.")
    if advisory:
        print(f"\nADVISORY (mined robustness — informational, does not gate; "
              f"--enforce-mined-robustness to gate): {len(advisory)}")
        for g in advisory[:10]:
            print(f"  • {g['status']:8} {g['category']}")
        if len(advisory) > 10:
            print(f"  … and {len(advisory) - 10} more")
    sys.exit(EXIT_GATED if gated else EXIT_OK)


if __name__ == "__main__":
    main()
