#!/usr/bin/env python3
"""
test_emit.py — deterministic tests for emit.py (no LLM calls).

emit's output is consumed by agent orchestrators, not humans: shape drift, dropped
evidence, or paraphrased acceptance criteria break downstream agents silently. These
tests pin the contract with a synthetic check.py verdict fixture.

Run: python3 test_emit.py  (or pytest test_emit.py)
"""
from __future__ import annotations
import json, subprocess, sys, unittest
from pathlib import Path

from emit import build_doc, gap_to_task, slug

EMIT = Path(__file__).resolve().parent / "emit.py"

# Synthetic check.py --json verdict. The 'fix_sites' / 'cited_files' keys on the second gap
# simulate the gap-schema growth another lane is shipping — emit must pass them through.
VERDICT = {
    "ok": False, "gated": True,
    "target": "/tmp/some-repo", "spine": "checklists/ai-agent-tool.features.json",
    "app_type": "ai-agent-tool", "sub_type": "agent CLI",
    "required_total": 9, "blocking_count": 2, "threshold": 0, "fail_on": "partial",
    "blocking_gaps": [
        {"category": "Config & Profiles", "status": "gap",
         "reasoning": "no config file support at all",
         "day1_tell": "Can a user persist a non-default model choice across runs?",
         "citation_unverified": False},
        {"category": "Session Persistence", "status": "partial",
         "reasoning": "history saved but not restorable",
         "day1_tell": "Kill the process mid-session; is the session resumable?",
         "citation_unverified": True,
         "fix_sites": ["src/session.py:42"], "cited_files": ["src/session.py"]},
    ],
}


def run_cli(args, stdin_text=None):
    return subprocess.run([sys.executable, str(EMIT), *args], input=stdin_text,
                          capture_output=True, text=True, cwd=EMIT.parent)


class TestEmit(unittest.TestCase):
    def test_doc_shape_is_stable(self):
        # intent: orchestrators parse this exact shape to spawn agents; a renamed or missing
        # key breaks every downstream queue consumer silently.
        doc = build_doc(VERDICT, "verdict")
        self.assertEqual(set(doc), {"tool", "version", "target", "spine", "generated_from",
                                    "task_count", "tasks"})
        self.assertEqual(doc["tool"], "2080-emit")
        self.assertEqual(doc["generated_from"], "verdict")
        self.assertEqual(doc["task_count"], 2)
        for t in doc["tasks"]:
            self.assertEqual(set(t), {"id", "title", "category", "tier", "status", "acceptance",
                                      "reasoning", "evidence", "verify_cmd"})

    def test_day1_tell_becomes_acceptance_verbatim(self):
        # intent: the day-1 tell is the measured acceptance criterion; a paraphrase would let
        # an implementing agent "pass" against a weaker bar than the spine mined.
        t = gap_to_task(VERDICT["blocking_gaps"][0], "/tmp/some-repo", "spine.json")
        self.assertEqual(t["acceptance"], "Can a user persist a non-default model choice across runs?")
        self.assertEqual(t["verify_cmd"], "check.py /tmp/some-repo --spine spine.json --json")

    def test_unknown_gap_keys_pass_through_to_evidence(self):
        # intent: another lane adds fix_sites to verdict gaps; emit dropping unknown keys would
        # strip the repair guidance agents need most.
        t = gap_to_task(VERDICT["blocking_gaps"][1], "x", "y")
        self.assertEqual(t["evidence"]["fix_sites"], ["src/session.py:42"])
        self.assertEqual(t["evidence"]["cited_files"], ["src/session.py"])
        self.assertTrue(t["evidence"]["citation_unverified"])
        self.assertNotIn("fix_sites", set(t) - {"evidence"})  # not promoted to a top-level field

    def test_battery_verdict_uses_per_gap_spine_in_verify_cmd(self):
        # intent: battery verdicts set the doc-level spine to None and carry the real one on
        # each gap; emit used to render `--spine None` — an un-runnable verify command that
        # defeats "closure is measured, not claimed" exactly when the user runs the full map.
        battery = {**VERDICT, "spine": None,
                   "spines": ["checklists/a.features.json", "checklists/a.operability.json"],
                   "blocking_gaps": [dict(VERDICT["blocking_gaps"][0],
                                          spine="checklists/a.features.json", axis="SCOPE")]}
        doc = build_doc(battery, "verdict")
        self.assertIn("--spine checklists/a.features.json", doc["tasks"][0]["verify_cmd"])
        self.assertNotIn("None", doc["tasks"][0]["verify_cmd"])
        self.assertIn("battery", doc["spine"])  # md header renders "2-spine battery", not "None"

    def test_verify_cmd_shell_quotes_hostile_target_and_spine(self):
        # intent: verify_cmd is BUILT TO BE RUN by an implementing agent, and target/spine
        # arrive from verdict JSON (stdin in pipe mode) — un-quoted shell metacharacters in a
        # path would execute when the agent runs the command verbatim.
        t = gap_to_task(VERDICT["blocking_gaps"][0], "/tmp/repo; rm -rf ~", "my spine.json")
        self.assertIn("'/tmp/repo; rm -rf ~'", t["verify_cmd"])
        self.assertIn("'my spine.json'", t["verify_cmd"])

    def test_empty_blocking_gaps_is_empty_queue_not_error(self):
        # intent: an open gate means "nothing to do" — emit must hand orchestrators an empty
        # queue with exit 0, not crash and stall the pipeline on the success case.
        clean = {**VERDICT, "ok": True, "gated": False, "blocking_gaps": []}
        r = run_cli(["--json"], stdin_text=json.dumps(clean))
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = json.loads(r.stdout)
        self.assertEqual(doc["task_count"], 0)
        self.assertEqual(doc["tasks"], [])

    def test_duplicate_categories_get_distinct_stable_ids(self):
        # intent: task ids key orchestrator state; two gaps in the same category colliding on
        # one id would silently merge two distinct work items.
        v = {**VERDICT, "blocking_gaps": [VERDICT["blocking_gaps"][0]] * 2}
        ids = [t["id"] for t in build_doc(v, "verdict")["tasks"]]
        self.assertEqual(ids, ["config-profiles", "config-profiles-2"])
        self.assertEqual(slug("Config & Profiles"), "config-profiles")

    def test_stdin_json_mode_emits_exactly_one_json_document(self):
        # intent: agents pipe check.py straight into emit.py; any non-JSON noise on stdout in
        # --json mode breaks the pipe contract.
        r = run_cli(["--json"], stdin_text=json.dumps(VERDICT))
        self.assertEqual(r.returncode, 0, r.stderr)
        doc = json.loads(r.stdout)  # raises if stdout isn't one clean document
        self.assertEqual(doc["task_count"], 2)
        self.assertEqual(doc["tasks"][1]["evidence"]["fix_sites"], ["src/session.py:42"])

    def test_md_format_renders_acceptance_checklist_per_task(self):
        # intent: the md backlog is what a human/agent reads to work the queue; a task section
        # without its acceptance checkbox is a spec with no done-condition.
        r = run_cli(["--format", "md"], stdin_text=json.dumps(VERDICT))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("## config-profiles — Close gap: Config & Profiles", r.stdout)
        self.assertIn("- [ ] Can a user persist a non-default model choice across runs?", r.stdout)
        self.assertIn("Complete partial: Session Persistence", r.stdout)

    def test_bare_json_invocation_prints_capability_map(self):
        # intent: agents introspect the tool via bare --json instead of scraping --help; losing
        # the capability map blinds unattended callers.
        # Subprocess stdin is a pipe (never a tty): blank stdin must still mean "no input",
        # because that's exactly how an unattended agent invokes the tool.
        r = run_cli(["--json"], stdin_text="")
        self.assertEqual(r.returncode, 0, r.stderr)
        cap = json.loads(r.stdout)
        self.assertEqual(cap["tool"], "2080-emit")
        self.assertEqual(set(cap), {"tool", "version", "args", "formats", "exit_codes"})

    def test_verdict_file_not_found_is_structured_exit_2(self):
        # intent: orchestrators branch on exit codes; a missing verdict file must be NOT_FOUND
        # (2) with JSON on stderr, not a Python traceback.
        r = run_cli(["--json", "--verdict", "/nonexistent/v.json"])
        self.assertEqual(r.returncode, 2)
        err = json.loads(r.stderr)
        self.assertEqual(err, {"ok": False, "error": "verdict not found: /nonexistent/v.json",
                               "exit_code": 2})


if __name__ == "__main__":
    unittest.main(verbosity=2)
