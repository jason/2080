#!/usr/bin/env python3
"""
test_init.py — deterministic tests for init.py (matched-spine acquisition glue).

No network, no LLM: these exercise the stage SEAMS — intent derivation, the harvest-JSON
contract cluster_fixes.py consumes, idempotent clone logic (fake git runner), and the
agentic CLI surface (capability map, --yes enforcement, --dry-run). The full live pipeline
(~30-60 min of LLM+network) is intentionally NOT run here.

Run: python3 -m unittest test_init -v
"""
from __future__ import annotations
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

import init

HERE = Path(__file__).resolve().parent
INIT = HERE / "init.py"
PY = sys.executable

README_FIXTURE = """\
# fancytool

[![CI](https://example.com/badge.svg)](https://example.com)
![logo](logo.png)

> A terminal multiplexer that coordinates multiple AI coding agents
> across persistent sessions.

## Install

pip install fancytool
"""


def run_cli(*args, env_extra=None):
    env = dict(os.environ, **(env_extra or {}))
    return subprocess.run([PY, str(INIT), *args], capture_output=True, text=True, env=env)


class TestIntentDerivation(unittest.TestCase):
    def test_first_paragraph_skips_heading_and_badges(self):
        # intent: a badge URL or "# title" line used as the mining intent sends
        # find_neighbors hunting the wrong neighbor class — the whole pipeline
        # then mines spines for the wrong app type.
        got = init.first_readme_paragraph(README_FIXTURE)
        self.assertEqual(got, "A terminal multiplexer that coordinates multiple "
                              "AI coding agents across persistent sessions.")

    def test_intent_flag_overrides_readme(self):
        # intent: a stale/marketing README must not be able to poison neighbor
        # discovery when the user explicitly states what they're building.
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "README.md").write_text(README_FIXTURE)
            intent, target = init.resolve_intent(d, "an ai agent CLI harness")
            self.assertEqual(intent, "an ai agent CLI harness")
            self.assertEqual(target, Path(d))

    def test_directory_without_readme_raises(self):
        # intent: silently mining with an empty intent would burn a ~$ LLM
        # discovery call on garbage; the failure must be loud and early.
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                init.resolve_intent(d, None)


class TestHarvestContract(unittest.TestCase):
    def test_harvest_shape_is_stable(self):
        # intent: harvests are the mine-input provenance record ({"project","commits":[{"sha",
        # "subject"}]}); consumers (archived cluster_fixes, future lenses) and humans rely on the
        # shape staying put — drift silently empties whatever reads it next.
        h = init.build_harvest(HERE, "2080", max_commits=0)
        self.assertEqual(set(h), {"project", "commits"})
        self.assertEqual(h["project"], "2080")
        self.assertGreater(len(h["commits"]), 0)
        for c in h["commits"]:
            self.assertEqual(set(c), {"sha", "subject"})
            self.assertRegex(c["sha"], r"^[0-9a-f]{40}$")
            self.assertTrue(c["subject"].strip())
        n = int(subprocess.run(["git", "-C", str(HERE), "rev-list", "--count", "HEAD"],
                               capture_output=True, text=True).stdout.strip())
        self.assertLessEqual(len(h["commits"]), n)  # ≤: empty-subject commits are dropped

    def test_harvest_respects_max_commits(self):
        # intent: --max-commits is the LLM-spend cap; ignoring it makes a
        # 20k-commit neighbor cost dollars and an hour in the abstraction pass.
        h = init.build_harvest(HERE, "2080", max_commits=3)
        self.assertEqual(len(h["commits"]), 3)
        newest = subprocess.run(["git", "-C", str(HERE), "log", "-1", "--format=%H"],
                                capture_output=True, text=True).stdout.strip()
        self.assertEqual(h["commits"][0]["sha"], newest)


class TestCloneIdempotence(unittest.TestCase):
    def test_clone_then_refresh(self):
        # intent: re-running init must refresh an existing cache clone, never
        # re-clone (slow, fails on existing dir) — init doubles as spine-update.
        calls = []
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "neighbors" / "repo"

            def fake_run(cmd, **kw):
                calls.append(cmd)
                if cmd[:2] == ["git", "clone"]:
                    (dest / ".git").mkdir(parents=True)
                return subprocess.CompletedProcess(cmd, 0, "", "")

            self.assertEqual(init.ensure_clone("owner/repo", dest, run=fake_run), "cloned")
            self.assertIn("--filter=blob:none", calls[0])  # full history, lazy blobs
            self.assertEqual(init.ensure_clone("owner/repo", dest, run=fake_run), "refreshed")
            self.assertFalse(any(c[:2] == ["git", "clone"] for c in calls[1:]))
            self.assertTrue(any("fetch" in c for c in calls[1:]))

    def test_clone_one_contains_failures_instead_of_raising(self):
        # intent: neighbors are cloned CONCURRENTLY (ex.map pool); a worker that raises
        # poisons the map and aborts the whole batch — one bad neighbor (malformed name,
        # failed clone) must degrade to a skip-with-reason so the healthy neighbors still
        # get harvested and mined.
        from unittest.mock import patch
        repo, name, dest, action, err = init.clone_one({"repo": "../../etc"})
        self.assertIsNone(action)
        self.assertIn("malformed", err)
        with patch.object(init, "ensure_clone", side_effect=RuntimeError("clone failed for o/r")):
            repo, name, dest, action, err = init.clone_one({"repo": "o/r"})
        self.assertIsNone(action)
        self.assertIn("clone failed", err)
        # not just RuntimeError: an OSError (mkdir, disk full) must be contained too
        with patch.object(init, "ensure_clone", side_effect=OSError("disk full")):
            repo, name, dest, action, err = init.clone_one({"repo": "o/r"})
        self.assertIsNone(action)
        self.assertIn("disk full", err)
        with patch.object(init, "ensure_clone", return_value="cloned"):
            repo, name, dest, action, err = init.clone_one({"repo": "o/r"})
        self.assertEqual((name, action, err), ("r", "cloned", None))

    def test_same_basename_neighbors_dont_share_a_clone_dir(self):
        # intent: apache/airflow and astronomer/airflow map to the SAME cache dir; cloned
        # concurrently they interleave writes into one working tree and the spine gets mined
        # from a corrupted clone — the later one must be skipped loudly, never raced.
        kept = init.dedupe_clone_dests([{"repo": "apache/airflow"},
                                        {"repo": "astronomer/airflow"},
                                        {"repo": "o/other"}])
        self.assertEqual([n["repo"] for n in kept], ["apache/airflow", "o/other"])

    def test_repo_name_traversal_rejected(self):
        # intent: a hostile/typo'd neighbor name like "../../etc" must not
        # become a cache path outside ~/.cache/2080 (path traversal).
        self.assertIsNone(init.REPO_RE.fullmatch("../../etc"))
        self.assertIsNone(init.REPO_RE.fullmatch("owner/repo/../.."))
        self.assertIsNotNone(init.REPO_RE.fullmatch("sst/opencode"))


class TestCLISurface(unittest.TestCase):
    def test_bare_json_capability_map(self):
        # intent: agentic callers introspect every 2080 tool via bare `--json`
        # (house contract); a missing/odd-shaped map breaks orchestrators.
        r = run_cli("--json")
        self.assertEqual(r.returncode, 0)
        cap = json.loads(r.stdout)
        self.assertEqual(cap["tool"], "2080-init")
        for key in ("version", "args", "exit_codes"):
            self.assertIn(key, cap)
        self.assertEqual(cap["exit_codes"]["0"], "ok")

    def test_json_mode_write_requires_yes(self):
        # intent: house rule — in --json mode any write needs explicit --yes;
        # an agent pipeline silently cloning+mining (~$, ~30min) is the failure.
        r = run_cli("an ai agent cli", "--json", "--neighbors", "owner/repo")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, "")  # stdout in JSON mode = one doc or nothing
        err = json.loads(r.stderr.strip().splitlines()[-1])
        self.assertFalse(err["ok"])
        self.assertEqual(err["exit_code"], 1)

    def test_dry_run_is_free_and_writes_nothing(self):
        # intent: --dry-run is the safe preview; if it ever hits network/LLM or
        # writes cache/checklists, previewing in CI becomes destructive+costly.
        with tempfile.TemporaryDirectory() as cache:
            r = run_cli(str(HERE), "--dry-run", "--json", env_extra={"CACHE_2080": cache})
            self.assertEqual(r.returncode, 0)
            plan = json.loads(r.stdout)  # exactly one JSON doc on stdout
            self.assertTrue(plan["ok"] and plan["dry_run"])
            self.assertTrue(plan["intent"])  # derived from 2080's own README
            self.assertIn("find_neighbors", str(plan["neighbors"]))
            self.assertIn("robustness", plan["would_mine"])
            self.assertIn("check.py", plan["next"])
            self.assertEqual(os.listdir(cache), [])  # zero writes

    def test_existing_spine_is_not_silently_overwritten(self):
        # intent: an LLM-classified app_type label is not unique — the first live
        # init run labeled a telegram-bot mine "ai-agent-tool" and silently
        # clobbered the aider/OI/gptme scope spine. The guard must refuse before
        # any clone/mine spend unless --force.
        with tempfile.TemporaryDirectory() as cache:
            r = run_cli("an ai agent cli", "--neighbors", "sst/opencode",
                        "--app-type", "ai-agent-cli",  # collides with the committed spine
                        "--json", "--yes", env_extra={"CACHE_2080": cache})
            self.assertEqual(r.returncode, 1)
            err = json.loads(r.stderr.strip().splitlines()[-1])
            self.assertFalse(err["ok"])
            self.assertIn("refusing to overwrite", err["error"])
            self.assertIn("--force", err["error"])
            self.assertEqual(os.listdir(cache), [])  # guard fired before any network spend

    def test_dry_run_with_neighbor_override_names_concrete_paths(self):
        # intent: with --neighbors the plan must show the exact clone dirs and
        # spine paths the live run would write, so a human can audit before --yes.
        with tempfile.TemporaryDirectory() as cache:
            r = run_cli("an ai agent cli", "--dry-run", "--json",
                        "--neighbors", "sst/opencode,block/goose",
                        env_extra={"CACHE_2080": cache})
            self.assertEqual(r.returncode, 0)
            plan = json.loads(r.stdout)
            self.assertEqual(plan["neighbors"], ["sst/opencode", "block/goose"])
            self.assertEqual(plan["would_clone"],
                             [f"{cache}/neighbors/opencode", f"{cache}/neighbors/goose"])
            self.assertNotIn("<", plan["app_type"])  # deterministic slug, no placeholder


if __name__ == "__main__":
    unittest.main()
