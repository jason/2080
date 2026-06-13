#!/usr/bin/env python3
"""
test_check_assessment.py — deterministic tests for the no-LLM gate path (check.py
--from-assessment) and the Stop hook built on it (hooks/stop_gate.sh).

These exercise the real CLI/hook boundary via subprocess — no fan, no network, no LLM —
so they are safe for CI and cost nothing. The live assess_target path is covered by a
manual smoke (one fan_call), not here.

Run: python3 test_check_assessment.py
"""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHECK = str(ROOT / "check.py")
HOOK = str(ROOT / "hooks" / "stop_gate.sh")

SPINE = {"app_type": "ai-agent-tool",
         "required": [{"category": "Config file support", "day1_tell": "look for a config loader"},
                      {"category": "Crash recovery", "day1_tell": "kill -9 mid-run and restart"}],
         "optional": []}


def make_assessment(cfg_status="gap", fix_sites=None):
    c1 = {"category": "Config file support", "tier": "required", "status": cfg_status,
          "reasoning": "no config loader anywhere in the tree", "day1_tell": "look for a config loader",
          "citation_unverified": False}
    if fix_sites:
        c1["fix_sites"] = fix_sites
    return {"sub_type": "test-cli", "app_type": "ai-agent-tool",
            "categories": [c1,
                           {"category": "Crash recovery", "tier": "required", "status": "covered",
                            "reasoning": "state journal + resume", "day1_tell": "", "citation_unverified": False}]}


def run_check(tmp, assessment, extra=(), assessment_file="asmt.json", spine_dict=None):
    """Write spine (+ assessment unless None) into tmp; run check.py --from-assessment --json."""
    spine = Path(tmp) / "spine.json"
    spine.write_text(json.dumps(spine_dict or SPINE))
    if assessment is not None:
        (Path(tmp) / assessment_file).write_text(json.dumps(assessment))
    return subprocess.run([sys.executable, CHECK, tmp, "--spine", str(spine),
                           "--from-assessment", str(Path(tmp) / assessment_file), "--json", *extra],
                          capture_output=True, text=True, cwd=ROOT)


class FromAssessmentGate(unittest.TestCase):
    def test_required_gap_gates_exit_3(self):
        # intent: a saved assessment with an open required gap must still block the build/stop —
        # otherwise the whole offline path silently rubber-stamps incomplete repos.
        with tempfile.TemporaryDirectory() as tmp:
            r = run_check(tmp, make_assessment("gap"))
            self.assertEqual(r.returncode, 3, r.stderr)
            v = json.loads(r.stdout)
            self.assertTrue(v["gated"])
            self.assertEqual(v["blocking_gaps"][0]["category"], "Config file support")

    def test_gaps_closed_passes_exit_0(self):
        # intent: once every required category is covered, the gate must open — a gate that can
        # never pass trains everyone to bypass it.
        with tempfile.TemporaryDirectory() as tmp:
            r = run_check(tmp, make_assessment("covered"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse(json.loads(r.stdout)["gated"])

    def test_missing_assessment_file_exits_not_found(self):
        # intent: CI/hooks branch on exit codes; a missing assessment must be NOT_FOUND (2),
        # not a crash (1) and never a fake pass (0).
        with tempfile.TemporaryDirectory() as tmp:
            r = run_check(tmp, None)
            self.assertEqual(r.returncode, 2, r.stderr)
            err = json.loads(r.stderr)
            self.assertFalse(err["ok"]); self.assertEqual(err["exit_code"], 2)

    def test_invalid_assessment_without_categories_errs(self):
        # intent: a truncated/corrupted saved assessment must fail loudly (exit 1), not gate on
        # an empty category list and report a bogus PASS.
        with tempfile.TemporaryDirectory() as tmp:
            r = run_check(tmp, {"sub_type": "x"})
            self.assertEqual(r.returncode, 1, r.stderr)

    def test_fix_sites_passthrough_in_json_verdict(self):
        # intent: diff_target is growing fix-site suggestions; if check.py drops them the agent
        # consuming the verdict loses the "where to fix it" half of the report.
        with tempfile.TemporaryDirectory() as tmp:
            r = run_check(tmp, make_assessment("gap", fix_sites=["src/config.py", "cli.py"]))
            self.assertEqual(r.returncode, 3, r.stderr)
            self.assertEqual(json.loads(r.stdout)["blocking_gaps"][0]["fix_sites"], ["src/config.py", "cli.py"])

    def test_verdict_summary_counts_statuses_by_tier(self):
        # intent: the summary block is the verdict's reporting surface (CI annotations,
        # dashboards) — miscounted health stats misreport project state to every consumer
        # that doesn't re-walk the category list itself.
        with tempfile.TemporaryDirectory() as tmp:
            r = run_check(tmp, make_assessment("gap"))
            v = json.loads(r.stdout)
            self.assertEqual(v["summary"], {"required": {"gap": 1, "covered": 1}})

    def test_fail_on_gap_does_not_block_partial(self):
        # intent: --fail-on gap is the lenient contract teams opt into; if partials still block,
        # the knob is a lie and thresholds get cranked instead.
        with tempfile.TemporaryDirectory() as tmp:
            r = run_check(tmp, make_assessment("partial"), extra=["--fail-on", "gap"])
            self.assertEqual(r.returncode, 0, r.stderr)


ROBUSTNESS_SPINE = {"app_type": "telegram-llm-bot", "lens": "recurring-fix", "axis": "ROBUSTNESS",
                    "required": [{"category": "dependency fix", "day1_tell": ""},
                                 {"category": "error handling", "origin": "generic-baseline", "day1_tell": ""}],
                    "optional": []}


def robustness_assessment(mined_status="gap", baseline_status="covered"):
    return {"sub_type": "test-bot", "app_type": "telegram-llm-bot",
            "categories": [
                {"category": "dependency fix", "tier": "required", "status": mined_status,
                 "reasoning": "change-shaped mined label", "day1_tell": "", "citation_unverified": False},
                {"category": "error handling", "tier": "required", "origin": "generic-baseline",
                 "status": baseline_status, "reasoning": "", "day1_tell": "", "citation_unverified": False}]}


class RobustnessAxisAdvisory(unittest.TestCase):
    def test_mined_robustness_gap_is_advisory_not_gating(self):
        # intent: mined robustness labels are change-shaped and lost to the generic baseline
        # (lift −0.15, ×3); gating on them produced 97/117 false-ish blocks on the first external
        # target. They must inform, not block — or the gate trains users to bypass it.
        with tempfile.TemporaryDirectory() as tmp:
            r = run_check(tmp, robustness_assessment("gap"), spine_dict=ROBUSTNESS_SPINE)
            self.assertEqual(r.returncode, 0, r.stderr)
            v = json.loads(r.stdout)
            self.assertFalse(v["gated"])
            self.assertEqual([g["category"] for g in v["advisory_gaps"]], ["dependency fix"])

    def test_baseline_floor_still_gates_on_robustness_axis(self):
        # intent: the generic baseline is the part of robustness that EARNED the gate (it beat
        # mining); demoting mined cats must not also open the gate for real floor gaps.
        with tempfile.TemporaryDirectory() as tmp:
            r = run_check(tmp, robustness_assessment("gap", baseline_status="gap"),
                          spine_dict=ROBUSTNESS_SPINE)
            self.assertEqual(r.returncode, 3, r.stderr)
            v = json.loads(r.stdout)
            self.assertEqual([g["category"] for g in v["blocking_gaps"]], ["error handling"])

    def test_enforce_mined_robustness_restores_full_gating(self):
        # intent: the escape hatch is the old contract — teams that want mined robustness to
        # block (e.g. after capability-phrased re-mining) must get exit 3 back with one flag.
        with tempfile.TemporaryDirectory() as tmp:
            r = run_check(tmp, robustness_assessment("gap"), spine_dict=ROBUSTNESS_SPINE,
                          extra=["--enforce-mined-robustness"])
            self.assertEqual(r.returncode, 3, r.stderr)

    def test_new_lens_axes_are_advisory_until_validated(self):
        # intent: every unvalidated mined axis (OPERABILITY/ISSUES/CONFIG/TESTS/DOCS) must demote
        # like ROBUSTNESS — a new lens silently gaining gating power is how unmeasured noise
        # starts blocking builds again.
        ops = {**ROBUSTNESS_SPINE, "lens": "operability-surface", "axis": "OPERABILITY"}
        with tempfile.TemporaryDirectory() as tmp:
            r = run_check(tmp, robustness_assessment("gap"), spine_dict=ops)
            self.assertEqual(r.returncode, 0, r.stderr)
            v = json.loads(r.stdout)
            self.assertEqual([g["category"] for g in v["advisory_gaps"]], ["dependency fix"])

    def test_scope_axis_mined_gaps_still_gate(self):
        # intent: scope mining WON its control (+0.27) — the robustness demotion must never
        # leak to SCOPE spines, or the one measured-valuable gate stops gating.
        scope = {**ROBUSTNESS_SPINE, "lens": "feature-surface", "axis": "SCOPE"}
        with tempfile.TemporaryDirectory() as tmp:
            r = run_check(tmp, robustness_assessment("gap"), spine_dict=scope)
            self.assertEqual(r.returncode, 3, r.stderr)
            self.assertEqual(json.loads(r.stdout)["advisory_count"], 0)


class UnassessedFailClosed(unittest.TestCase):
    """A required category whose status is still 'unknown' was never judged (failed/timed-out
    assessment chunk). 'We couldn't assess it' must never render as 'doesn't block'."""

    def unknown_assessment(self):
        a = make_assessment("covered")
        a["categories"][1]["status"] = "unknown"  # Crash recovery: chunk failed, never judged
        return a

    def test_unknown_required_category_refuses_pass(self):
        # intent: a transient 429/timeout on one assessment chunk used to flip GATED→PASS —
        # the worst-direction failure for a completeness gate. Unassessed must fail closed
        # (exit 1, ok:false), distinct from GATED (3), so CI can tell "incomplete" from "gaps".
        with tempfile.TemporaryDirectory() as tmp:
            r = run_check(tmp, self.unknown_assessment())
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            v = json.loads(r.stdout)
            self.assertFalse(v["ok"])
            self.assertEqual(v["unassessed_count"], 1)
            self.assertFalse(v["gated"])  # not gaps — incompleteness

    def test_allow_unassessed_restores_pass(self):
        # intent: --allow-unassessed is the explicit opt-out (e.g. a known-flaky advisory spine);
        # without a working escape hatch teams would fork the gate instead of configuring it.
        with tempfile.TemporaryDirectory() as tmp:
            r = run_check(tmp, self.unknown_assessment(), extra=["--allow-unassessed"])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            v = json.loads(r.stdout)
            self.assertTrue(v["ok"])
            self.assertEqual(v["unassessed_count"], 1)  # still visible, just not blocking

    def test_real_gaps_still_dominate_unknowns(self):
        # intent: when real blocking gaps AND unknowns coexist, GATED (3) is the actionable
        # verdict — exit 1 would hide the closable gap list behind an "incomplete" error.
        with tempfile.TemporaryDirectory() as tmp:
            a = make_assessment("gap")
            a["categories"][1]["status"] = "unknown"
            r = run_check(tmp, a)
            self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
            v = json.loads(r.stdout)
            self.assertTrue(v["gated"])
            self.assertEqual(v["unassessed_count"], 1)


class BatteryMode(unittest.TestCase):
    """Multi-spine day-1 map: gating axes block, advisory axes inform, one merged verdict."""

    def setup_battery(self, tmp):
        scope = {"app_type": "telegram-llm-bot", "lens": "feature-surface", "axis": "SCOPE",
                 "required": [{"category": "Web dashboard", "day1_tell": ""}], "optional": []}
        ops = {"app_type": "telegram-llm-bot", "lens": "operability-surface", "axis": "OPERABILITY",
               "required": [{"category": "containerization", "day1_tell": ""}], "optional": []}
        (Path(tmp) / "scope.json").write_text(json.dumps(scope))
        (Path(tmp) / "ops.json").write_text(json.dumps(ops))
        asmts = {"scope": {"sub_type": "t", "app_type": "telegram-llm-bot", "axis": "SCOPE",
                           "categories": [{"category": "Web dashboard", "tier": "required",
                                           "status": "gap", "reasoning": "", "day1_tell": "",
                                           "citation_unverified": False}]},
                 "ops": {"sub_type": "t", "app_type": "telegram-llm-bot", "axis": "OPERABILITY",
                         "categories": [{"category": "containerization", "tier": "required",
                                         "status": "gap", "reasoning": "", "day1_tell": "",
                                         "citation_unverified": False}]}}
        d = Path(tmp) / "asmts"; d.mkdir()
        for stem, asmt in asmts.items():
            (d / f"{stem}.assessment.json").write_text(json.dumps(asmt))
        return d

    def run_battery(self, tmp, extra=()):
        return subprocess.run([sys.executable, CHECK, tmp,
                               "--spine", str(Path(tmp) / "scope.json"), str(Path(tmp) / "ops.json"),
                               "--from-assessment", str(Path(tmp) / "asmts"), "--json", *extra],
                              capture_output=True, text=True, cwd=ROOT)

    def test_battery_merges_gating_and_advisory_by_axis(self):
        # intent: the day-1 map is ONE verdict across spines — SCOPE gaps must block (exit 3)
        # while OPERABILITY gaps ride along as advisory; collapsing both into blocking would
        # re-create the 97-block noise, dropping either would hide real findings from emit.
        with tempfile.TemporaryDirectory() as tmp:
            self.setup_battery(tmp)
            r = self.run_battery(tmp)
            self.assertEqual(r.returncode, 3, r.stderr)
            v = json.loads(r.stdout)
            self.assertEqual([g["category"] for g in v["blocking_gaps"]], ["Web dashboard"])
            self.assertEqual([g["category"] for g in v["advisory_gaps"]], ["containerization"])
            self.assertEqual(v["blocking_gaps"][0]["axis"], "SCOPE")
            self.assertEqual(len(v["per_spine"]), 2)

    def test_battery_missing_assessment_dir_is_not_found(self):
        # intent: CI re-gates from the saved directory; pointing at a missing/wrong path must be
        # exit 2 (regenerate), never a crash or a silent pass over zero spines.
        with tempfile.TemporaryDirectory() as tmp:
            self.setup_battery(tmp)
            r = subprocess.run([sys.executable, CHECK, tmp,
                                "--spine", str(Path(tmp) / "scope.json"), str(Path(tmp) / "ops.json"),
                                "--from-assessment", str(Path(tmp) / "nope"), "--json"],
                               capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(r.returncode, 2, r.stderr)


class StopHook(unittest.TestCase):
    def hook(self, tmp, stdin="{}"):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": tmp}
        return subprocess.run(["bash", HOOK], input=stdin, capture_output=True, text=True,
                              env=env, cwd=tmp)

    def setup_gated_repo(self, tmp):
        (Path(tmp) / "spine.json").write_text(json.dumps(SPINE))
        (Path(tmp) / ".2080-assessment.json").write_text(json.dumps(make_assessment("gap")))
        (Path(tmp) / ".2080.json").write_text(json.dumps(
            {"spine": "spine.json", "threshold": 0, "fail_on": "partial",
             "mode": "assessment", "assessment": ".2080-assessment.json"}))

    def test_hook_blocks_on_closed_gate_with_gap_summary(self):
        # intent: the whole point of the Stop hook — an agent cannot claim "done" while required
        # gaps remain, and stderr must name the gaps so the agent knows what to close.
        with tempfile.TemporaryDirectory() as tmp:
            self.setup_gated_repo(tmp)
            r = self.hook(tmp)
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("Config file support", r.stderr)

    def test_hook_fails_open_without_config(self):
        # intent: repos that never opted into 2080 must be untouched — a gate that wedges
        # unconfigured sessions would get the hook uninstalled everywhere.
        with tempfile.TemporaryDirectory() as tmp:
            r = self.hook(tmp)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stderr, "")

    def test_hook_fails_open_on_missing_assessment(self):
        # intent: a configured repo whose assessment file was deleted/never generated must fail
        # OPEN, not block the user behind a gate that cannot be evaluated.
        with tempfile.TemporaryDirectory() as tmp:
            self.setup_gated_repo(tmp)
            (Path(tmp) / ".2080-assessment.json").unlink()
            r = self.hook(tmp)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_hook_honors_stop_hook_active_loop_guard(self):
        # intent: Claude Code re-fires Stop hooks after a block; without honoring
        # stop_hook_active a gated session could never end — an unkillable hook.
        with tempfile.TemporaryDirectory() as tmp:
            self.setup_gated_repo(tmp)
            r = self.hook(tmp, stdin=json.dumps({"stop_hook_active": True}))
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_hook_passes_when_gate_open(self):
        # intent: closed gaps must let the session end normally — exit 0, no noise that would
        # show up as a phantom block reason.
        with tempfile.TemporaryDirectory() as tmp:
            self.setup_gated_repo(tmp)
            (Path(tmp) / ".2080-assessment.json").write_text(json.dumps(make_assessment("covered")))
            r = self.hook(tmp)
            self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
