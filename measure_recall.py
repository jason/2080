#!/usr/bin/env python3
"""
measure_recall.py — gate RECALL against a repo's own future (the missing half of gate quality).

Precision (0.77, adversarial two-lens refutation) says blocking verdicts are usually right.
This measures the other failure mode: how much GENUINELY-UPCOMING work does the gate MISS
(false 'covered'/'na' verdicts = blind spots)?

Protocol (ground truth by construction, no hand labels):
  1. Snapshot a cloned neighbor repo PART-WAY through its FULL history (--snapshot-frac of all
     commits already happened; the rest is its "future"). Full history, NOT the capped harvest
     window — v0.1 snapshotted inside the recent-500 harvest and "75% back" was still the mature
     product, so ground truth was contaminated with already-covered capabilities.
  2. Ground truth G = spine categories that the repo's FUTURE commits demonstrably introduced —
     mapped by J STRICT single-best-match judges (measure.py's prompt discipline: direct
     INSTANCE + introduces-the-capability, null when unsure; a mapping counts only when ALL
     judges agree), kept when >= --min-commits distinct future commits agree (recurring signal,
     not a one-off).
  3. Run the REAL assessor (diff_target.assess_target) on the snapshot worktree, --runs times.
  4. recall = |G flagged gap/partial| / |G| per run. Misses are printed with the verdict they
     got — each is a measured blind spot.

KNOWN LIMITATION (printed in output): the spine was mined from this repo's own full history
(self-prediction). That inflates SPINE coverage, but the measured quantity is the ASSESSOR's
recall given a category is in the spine and genuinely upcoming — the assessment never sees
future commits. A leave-one-out spine is the cleaner follow-up.

Usage: measure_recall.py [--repo LangBot] [--spine checklists/telegram-llm-bot.features.json]
                         [--snapshot-frac 0.25] [--min-commits 2] [--judges 2] [--runs 2] [--json]
Exit codes: 0 ok | 1 usage/err | 2 not_found | 3 empty (no ground truth survived the judges)
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path

from mine_common import fan_batch, extract_json, EXIT_OK, EXIT_ERR, EXIT_NOT_FOUND, EXIT_EMPTY

CACHE = Path(os.environ.get("CACHE_2080", os.path.expanduser("~/.cache/2080")))
FLAGGED = {"gap", "partial"}


def capability_map():
    return {"tool": "measure_recall", "version": "0.1",
            "args": "[--repo NAME] [--spine FILE] [--snapshot-frac F] [--min-commits N] "
                    "[--judges J] [--runs R] [--json]",
            "exit_codes": {"0": "ok", "1": "usage/err", "2": "not_found", "3": "empty ground truth"}}


def split_at(commits, frac):
    """Commits are newest-first. Snapshot so that `frac` of the history has already happened:
    snapshot index k = int(len * (1 - frac)); future = commits[:k] (pure)."""
    k = int(len(commits) * (1 - frac))
    k = max(1, min(k, len(commits) - 1))
    return commits[:k], commits[k]["sha"]


def sample_even(commits, cap):
    """Evenly-spaced sample across the whole future (pure). Judging only the newest slice would
    miss capabilities introduced early in the future; only the oldest would miss late ones."""
    if len(commits) <= cap:
        return commits
    step = len(commits) / cap
    return [commits[int(i * step)] for i in range(cap)]


def repo_commits(repo_dir):
    """Full history (newest-first) from the clone: [{'sha','subject'}]."""
    r = subprocess.run(["git", "-C", str(repo_dir), "log", "--format=%H%x09%s"],
                       capture_output=True, text=True, check=True, timeout=120)
    return [{"sha": ln.split("\t", 1)[0], "subject": ln.split("\t", 1)[1] if "\t" in ln else ""}
            for ln in r.stdout.splitlines() if ln]


def judge_future_calls(future, cats, judges):
    """STRICT introduction-judge calls: map each future commit subject to the ONE spine category
    it INTRODUCES, or null. Same chunking discipline as measure.py (pure)."""
    calls, CH = [], 18
    listing_cats = "\n".join(f"- {c['category']}" for c in cats)
    for ci in range(0, len(future), CH):
        chunk = future[ci:ci + CH]
        listing = "\n".join(f"{j+1}. {c['subject']}" for j, c in enumerate(chunk))
        prompt = (f"PREDICTED capability categories for this app type:\n{listing_cats}\n\n"
                  f"Commits this project shipped LATER in its life:\n{listing}\n\n"
                  "For each commit, name the SINGLE category above that the commit is a DIRECT "
                  "INSTANCE of, and ONLY if the commit INTRODUCES or substantially builds out that "
                  "capability (a new feature/surface) — NOT routine maintenance, bugfixing, or polish "
                  "of something that already exists. If it only loosely relates, is maintenance, or "
                  "matches none, return null. Be STRICT — when unsure, return null. "
                  'Return ONLY JSON {number: {"cat": "<exact category label or null>"}}.')
        for jdg in range(judges):
            calls.append({"id": f"recall|{ci}|{jdg}", "prompt": prompt, "maxTokens": 1100,
                          "_chunk_start": ci, "_n": len(chunk)})
    return calls


def agreed_mappings(calls, results, judges):
    """Per-commit category votes -> mappings where ALL judges named the same category (pure).
    Returns {commit_index: category_label_lower}."""
    votes = {}  # (chunk_start, j) -> [labels]
    for call in calls:
        m = extract_json(results.get(call["id"]) or "") or {}
        for j in range(call["_n"]):
            v = m.get(str(j + 1)) or m.get(j + 1) or {}
            lab = (v.get("cat") if isinstance(v, dict) else v) or None
            lab = lab.strip().lower() if isinstance(lab, str) and lab.strip().lower() not in ("null", "none", "") else None
            votes.setdefault((call["_chunk_start"], j), []).append(lab)
    out = {}
    for (ci, j), labs in votes.items():
        if len(labs) == judges and labs[0] is not None and all(l == labs[0] for l in labs):
            out[ci + j] = labs[0]
    return out


def ground_truth(mappings, cats, min_commits):
    """Categories with >= min_commits distinct agreed future commits (pure). Lowercase labels,
    restricted to real spine categories (judges can't invent one)."""
    valid = {c["category"].lower() for c in cats}
    counts = {}
    for lab in mappings.values():
        if lab in valid:
            counts[lab] = counts.get(lab, 0) + 1
    return sorted(lab for lab, n in counts.items() if n >= min_commits)


def recall_of_run(gt, assessment):
    """recall + misses for one assessment run (pure). Misses carry the verdict they got."""
    verdicts = {c["category"].lower(): c.get("status", "unknown") for c in assessment["categories"]}
    hit = [g for g in gt if verdicts.get(g) in FLAGGED]
    misses = {g: verdicts.get(g, "absent-from-assessment") for g in gt if g not in hit}
    return (len(hit) / len(gt) if gt else 0.0), misses


def make_snapshot(repo_dir, sha):
    wt = Path(f"/tmp/2080-recall-{repo_dir.name}-{sha[:8]}")
    if not wt.exists():
        subprocess.run(["git", "-C", str(repo_dir), "worktree", "add", "--force", str(wt), sha],
                       check=True, capture_output=True, text=True, timeout=300)
    return wt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="LangBot", help="harvested neighbor name under ~/.cache/2080/")
    ap.add_argument("--spine", default="checklists/telegram-llm-bot.features.json")
    ap.add_argument("--snapshot-frac", type=float, default=0.25,
                    help="fraction of the repo's FULL history already happened at snapshot (rest = future)")
    ap.add_argument("--future-cap", type=int, default=400,
                    help="judge at most this many future commits (evenly sampled across the future)")
    ap.add_argument("--min-commits", type=int, default=2)
    ap.add_argument("--judges", type=int, default=2)
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    repo_dir = CACHE / "neighbors" / a.repo
    spine_path = Path(a.spine)
    for p, what in ((repo_dir, "neighbor clone"), (spine_path, "spine")):
        if not p.exists():
            print(json.dumps({"ok": False, "error": f"{what} not found: {p}", "exit_code": EXIT_NOT_FOUND})
                  if a.json else f"{what} not found: {p}", file=sys.stderr)
            sys.exit(EXIT_NOT_FOUND)

    cl = json.loads(spine_path.read_text())
    cats = cl.get("required", [])
    commits = repo_commits(repo_dir)
    all_future, snap_sha = split_at(commits, a.snapshot_frac)
    future = sample_even(all_future, a.future_cap)

    print(f"[1/3] history {len(commits)} commits; snapshot after {len(commits) - len(all_future)}; "
          f"judging {len(future)}/{len(all_future)} future commits vs {len(cats)} required categories "
          f"({a.judges} strict judges, agreement required)…", file=sys.stderr)
    calls = judge_future_calls(future, cats, a.judges)
    results = fan_batch(calls)
    gt = ground_truth(agreed_mappings(calls, results, a.judges), cats, a.min_commits)
    if not gt:
        print(json.dumps({"ok": False, "error": "no ground-truth categories survived the judges",
                          "exit_code": EXIT_EMPTY}) if a.json else "no ground truth survived", file=sys.stderr)
        sys.exit(EXIT_EMPTY)

    print(f"[2/3] snapshot worktree @ {snap_sha[:8]} ({len(all_future)} commits before repo HEAD)…", file=sys.stderr)
    wt = make_snapshot(repo_dir, snap_sha)

    from diff_target import assess_target  # late import: keeps --json capability map LLM-free
    runs = []
    for r in range(a.runs):
        print(f"[3/3] assessment run {r + 1}/{a.runs}…", file=sys.stderr)
        result = assess_target(str(wt), cl)
        if not result:
            print(f"run {r + 1} failed (unparseable assessment) — skipped", file=sys.stderr)
            continue
        rec, misses = recall_of_run(gt, result)
        runs.append({"recall": round(rec, 3), "misses": misses})
    if not runs:
        print("all assessment runs failed", file=sys.stderr); sys.exit(EXIT_ERR)

    recalls = [r["recall"] for r in runs]
    report = {"ok": True, "repo": a.repo, "spine": str(spine_path), "snapshot_sha": snap_sha,
              "history_commits": len(commits), "future_commits": len(all_future),
              "future_judged": len(future), "ground_truth": gt, "n_ground_truth": len(gt),
              "runs": runs, "mean_recall": round(sum(recalls) / len(recalls), 3),
              "recall_spread": round(max(recalls) - min(recalls), 3),
              "limitation": "self-prediction: spine mined from this repo's full history; assessor "
                            "never sees future commits, but a leave-one-out spine is cleaner"}
    if a.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"\nGATE RECALL — {a.repo} @ {snap_sha[:8]} vs {spine_path.name}")
        print(f"ground truth ({len(gt)} categories the repo later introduced): {', '.join(gt)}")
        for i, r in enumerate(runs):
            miss = "; ".join(f"{k} (got {v})" for k, v in r["misses"].items()) or "none"
            print(f"run {i + 1}: recall {r['recall']:.2f} | missed: {miss}")
        print(f"mean recall {report['mean_recall']:.2f} (spread {report['recall_spread']:.2f} across {len(runs)} runs)")
        print(f"limitation: {report['limitation']}")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--json":
        print(json.dumps(capability_map())); sys.exit(EXIT_OK)
    main()
