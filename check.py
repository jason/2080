#!/usr/bin/env python3
"""
check.py — 2080's KEYSTONE gate. `2080 check`: is this target's second-85% closed enough to ship?

One command unifies three capabilities the feature-spine dogfood flagged as 2080's own gaps,
each by exposing a primitive 2080 already has:

  CUSTOM RULES  ← the spine/checklist (--spine) IS the rule set; lenses (cluster_fixes / lens_mine)
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

from mine_common import EXIT_OK, EXIT_ERR, EXIT_NOT_FOUND, llm_runtime
from diff_target import assess_target

EXIT_GATED = 3  # mirrors rally-flow's gate() exit code: completion refused


def capability_map():
    return {"tool": "2080-check", "version": "0.2",
            "args": "<target-repo> --spine <checklist.json> [--threshold N] [--fail-on gap|partial] "
                    "[--save-assessment FILE] [--from-assessment FILE] [--json] [--yes]",
            "fail_on": ["gap", "partial"],
            "axis_gating": "mined categories gate only on validated axes (SCOPE); other axes are "
                           "advisory by default with the generic-baseline floor still gating; "
                           "--enforce-mined restores full gating",
            "llm": llm_runtime(),  # bring-your-own-key preflight: backend/model/key SOURCE (never values)
            "assessment": {"--save-assessment": "after the live LLM assess, write the raw assessment JSON to FILE",
                           "--from-assessment": "skip the LLM: load a saved assessment and gate on it (deterministic)"},
            "exit_codes": {"0": "pass (gate open)", "1": "usage/err", "2": "not_found", "3": "gated (required gaps remain)"}}


def die(msg, code, as_json):
    """Errors go to stderr; structured {ok:false,...} when --json so agents never parse prose."""
    print(json.dumps({"ok": False, "error": msg, "exit_code": code}) if as_json else msg, file=sys.stderr)
    sys.exit(code)


# Axes that beat the generic-baseline control (measure.py, strict judges, ×3 with variance):
#   SCOPE  +0.27 ±0.05 (2026-06, feature-surface, ai-agent-tool targets dexto/goose/cline)
#   ISSUES +0.41 ±0.06 on scope-layer work; +0.02 ±0.03 (baseline-parity, not harmful) on
#          robustness-layer (2026-06-11, issue-surface ai-agent-cli spine, same targets/protocol)
# Every other axis is advisory until it passes the same bar.
VALIDATED_GATING_AXES = {"SCOPE", "ISSUES"}


def evaluate(result, fail_on, axis=None, enforce_mined_robustness=False):
    """Split assessed categories into blocking (applicable required gaps), advisory, and the rest.
    Blocking = tier==required AND status in fail_on AND not na_by_design/covered.

    Axis discipline: mined categories GATE only on validated axes (SCOPE +0.27, ISSUES +0.41 —
    see VALIDATED_GATING_AXES). On every other mined axis (ROBUSTNESS, CONFIG, TESTS, DOCS,
    OPERABILITY…) they are ADVISORY — informative, never blocking — until that lens beats
    the same control. Measured for ROBUSTNESS (2026-06, ×3): the generic checklist out-recalls
    the mined spine (−0.15) and change-shaped labels caused 97/117 false-ish blocks on the first
    external target. The `origin: generic-baseline` floor always gates. A spine with NO axis
    (user-authored checklist) gates in full — it's the user's own rule set."""
    block_statuses = {"gap", "partial"} if fail_on == "partial" else {"gap"}
    demote_mined = bool(axis) and (axis or "").upper() not in VALIDATED_GATING_AXES \
        and not enforce_mined_robustness
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


def load_or_assess(target, spine_path, cl, a, save_to=None, from_file=None):
    """One spine's assessment: loaded from a saved file, or live via assess_target."""
    if from_file:
        if not from_file.exists():
            die(f"assessment not found: {from_file} (generate with --save-assessment)", EXIT_NOT_FOUND, a.json)
        try:
            result = json.loads(from_file.read_text())
        except Exception as e:
            die(f"assessment unreadable: {from_file}: {e}", EXIT_ERR, a.json)
        if not isinstance(result, dict) or not isinstance(result.get("categories"), list):
            die(f"invalid assessment (no 'categories' list): {from_file}", EXIT_ERR, a.json)
        return result
    result = assess_target(target, cl)
    if not result:
        die(f"assessment failed for {spine_path.name} (could not parse model output)", EXIT_ERR, a.json)
    if save_to:
        save_to.write_text(json.dumps(result, indent=2) + "\n")
    return result


def print_gaps(gaps, fix_sites=True):
    for g in gaps:
        flag = " ⚠unverified-citation" if g["citation_unverified"] else ""
        icon = "❌" if g["status"] == "gap" else "🟡"
        print(f"  {icon} {g['status']:8} {g['category']}{flag}")
        if g["reasoning"]:
            print(f"        ↳ {g['reasoning'][:140]}")
        if g["day1_tell"]:
            print(f"        check: {g['day1_tell'][:120]}")
        if fix_sites and g.get("fix_sites"):
            for s in g["fix_sites"][:3]:
                if isinstance(s, dict):
                    print(f"        fix @ {s.get('file', '?')}: {str(s.get('what', ''))[:110]}")
                else:
                    print(f"        fix @ {str(s)[:120]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?")
    ap.add_argument("--spine", "--checklist", dest="spine", nargs="+", action="extend",
                    help="checklist/spine JSON(s); several (or a shell glob) = battery mode with one merged day-1 map")
    ap.add_argument("--threshold", type=int, default=0, help="max applicable required gaps allowed before the gate blocks")
    ap.add_argument("--fail-on", choices=["gap", "partial"], default="partial",
                    help="'gap' blocks only on full gaps; 'partial' (default) also blocks on partials")
    ap.add_argument("--enforce-mined", "--enforce-mined-robustness", dest="enforce_mined_robustness",
                    action="store_true",
                    help="gate on mined categories of non-validated axes too (default: only SCOPE-axis "
                         "mined categories and the generic-baseline floor gate; the rest are advisory)")
    ap.add_argument("--save-assessment", metavar="PATH",
                    help="write the raw assessment JSON to PATH (battery mode: a directory, one file per spine)")
    ap.add_argument("--from-assessment", metavar="PATH",
                    help="skip the LLM: gate on saved assessment(s) at PATH (battery mode: the directory "
                         "--save-assessment wrote; deterministic, CI/hook-safe)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--yes", "-y", action="store_true", help="accepted for agentic use; check is read-only")
    a = ap.parse_args()

    if not a.target:
        if a.json:
            print(json.dumps(capability_map())); sys.exit(EXIT_OK)
        print(capability_map()["args"], file=sys.stderr); sys.exit(EXIT_ERR)
    if not a.spine:
        die("--spine <checklist.json>... is required", EXIT_ERR, a.json)
    if not Path(a.target).exists():
        die(f"target not found: {a.target}", EXIT_NOT_FOUND, a.json)
    for s in a.spine:
        if not Path(s).exists():
            die(f"spine not found: {s}", EXIT_NOT_FOUND, a.json)
    battery = len(a.spine) > 1

    save_dir = from_dir = None
    if battery:
        if a.save_assessment:
            save_dir = Path(a.save_assessment); save_dir.mkdir(parents=True, exist_ok=True)
        if a.from_assessment:
            from_dir = Path(a.from_assessment)
            if not from_dir.is_dir():
                die(f"battery --from-assessment must be the directory --save-assessment wrote: {from_dir}",
                    EXIT_NOT_FOUND, a.json)

    runs = []
    for s in a.spine:
        spine_path = Path(s)
        cl = json.loads(spine_path.read_text())
        save_to = (save_dir / f"{spine_path.stem}.assessment.json") if save_dir else \
            (Path(a.save_assessment) if (a.save_assessment and not battery) else None)
        from_file = (from_dir / f"{spine_path.stem}.assessment.json") if from_dir else \
            (Path(a.from_assessment) if (a.from_assessment and not battery) else None)
        result = load_or_assess(a.target, spine_path, cl, a, save_to=save_to, from_file=from_file)
        axis = result.get("axis") or cl.get("axis")  # old saved assessments lack axis; the spine has it
        blocking, advisory, required_total = evaluate(result, a.fail_on, axis=axis,
                                                      enforce_mined_robustness=a.enforce_mined_robustness)
        runs.append({"spine": str(spine_path), "app_type": cl.get("app_type"),
                     "sub_type": result.get("sub_type", "?"), "axis": axis,
                     "required_total": required_total,
                     "blocking_count": len(blocking), "advisory_count": len(advisory),
                     "blocking_gaps": blocking, "advisory_gaps": advisory})

    all_blocking = [dict(g, spine=r["spine"], axis=r["axis"]) for r in runs for g in r["blocking_gaps"]] \
        if battery else runs[0]["blocking_gaps"]
    all_advisory = [dict(g, spine=r["spine"], axis=r["axis"]) for r in runs for g in r["advisory_gaps"]] \
        if battery else runs[0]["advisory_gaps"]
    gated = max(0, len(all_blocking) - a.threshold) > 0
    verdict = {
        "ok": not gated,
        "gated": gated,
        "target": a.target,
        "spine": runs[0]["spine"] if not battery else None,
        "spines": [r["spine"] for r in runs],
        "app_type": runs[0]["app_type"],
        "sub_type": runs[0]["sub_type"],
        "axis": runs[0]["axis"] if not battery else None,
        "required_total": sum(r["required_total"] for r in runs),
        "blocking_count": len(all_blocking),
        "advisory_count": len(all_advisory),
        "threshold": a.threshold,
        "fail_on": a.fail_on,
        "blocking_gaps": all_blocking,
        "advisory_gaps": all_advisory,
    }
    if battery:
        verdict["per_spine"] = [{k: r[k] for k in ("spine", "axis", "required_total",
                                                   "blocking_count", "advisory_count")} for r in runs]

    if a.json:
        print(json.dumps(verdict, indent=2))
        sys.exit(EXIT_GATED if gated else EXIT_OK)

    head = "🚫 GATED" if gated else "✅ PASS"
    if not battery:
        r = runs[0]
        print(f"{head} — {a.target} vs {r['app_type']} spine ({Path(r['spine']).name})")
        print(f"sub_type: {r['sub_type']}")
        print(f"required: {r['required_total']} | blocking (applicable required {a.fail_on}s): "
              f"{len(all_blocking)} | threshold: {a.threshold}\n")
    else:
        print(f"{head} — {a.target} day-1 map ({len(runs)} spines, {verdict['required_total']} required categories)")
        print(f"sub_type: {runs[0]['sub_type']}")
        print(f"blocking: {len(all_blocking)} (gating axes) | advisory: {len(all_advisory)} "
              f"| threshold: {a.threshold}\n")
    if all_blocking:
        print("BLOCKING GAPS (close these to open the gate):")
        print_gaps(all_blocking)
    else:
        print("No applicable required gaps remain — the gating surface is closed.")
    if not battery:
        if all_advisory:
            print(f"\nADVISORY (mined {runs[0]['axis'] or '?'}-axis — informational, does not gate; "
                  f"--enforce-mined to gate): {len(all_advisory)}")
            for g in all_advisory[:10]:
                print(f"  • {g['status']:8} {g['category']}")
            if len(all_advisory) > 10:
                print(f"  … and {len(all_advisory) - 10} more")
    else:
        for r in runs:
            if not r["advisory_gaps"]:
                continue
            print(f"\nADVISORY — {r['axis'] or '?'} ({Path(r['spine']).name}): "
                  f"{r['advisory_count']} of {r['required_total']} required")
            for g in r["advisory_gaps"][:8]:
                print(f"  • {g['status']:8} {g['category']}")
                if g.get("day1_tell"):
                    print(f"        check: {g['day1_tell'][:110]}")
            if r["advisory_count"] > 8:
                print(f"  … and {r['advisory_count'] - 8} more")
        print("\n(advisory sections inform the day-1 map; only gating axes block. --enforce-mined to gate them)")
    sys.exit(EXIT_GATED if gated else EXIT_OK)


if __name__ == "__main__":
    main()
