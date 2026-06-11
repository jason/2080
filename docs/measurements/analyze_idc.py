#!/usr/bin/env python3
"""ISSUES foreign-domain specificity + DISCUSSIONS lift, from the combined measure.py run.

Pre-registered rules (set before the run):
  ISSUES: foreign specificity = in(cli) - out(tmux/zellij). Demote if <= baseline's + 0.05;
          affirm if >= 2x baseline's; otherwise flag and keep.
  DISCUSSIONS: scope-layer lift vs baseline on telegram targets, x3. Record only (promotion
          additionally needs its own specificity pass). Candidate bar: >= +0.15, all runs positive,
          AND specificity (in=telegram, out=cli+mux) > baseline's by >= 0.05.
"""
import json

d = json.load(open("/tmp/issues-discussions-control.json"))
CLI, MUX, TG = {"dexto", "goose", "cline"}, {"tmux", "zellij"}, {"nekro", "n3dbot", "karfly"}
pt = d["per_target"]

def recall(variant, targets, layer="scope"):
    vals = []
    for t in targets:
        vd = (pt.get(t, {}).get(layer) or {}).get("variants", {}).get(variant)
        rs = [r["llm_real"] for r in (vd or {}).get("llm_runs", []) if r.get("llm_real") is not None]
        if rs:
            vals.append(sum(rs) / len(rs))
    return sum(vals) / len(vals) if vals else None

def runs(variant, targets, layer="scope"):
    """Per-repeat mean over targets (paired across targets within a repeat)."""
    per_run = []
    for i in range(d.get("repeats", 3)):
        vals = []
        for t in targets:
            vd = (pt.get(t, {}).get(layer) or {}).get("variants", {}).get(variant)
            if vd and len(vd.get("llm_runs", [])) > i and vd["llm_runs"][i].get("llm_real") is not None:
                vals.append(vd["llm_runs"][i]["llm_real"])
        if vals:
            per_run.append(sum(vals) / len(vals))
    return per_run

names = list(next(iter(pt.values()))["scope"]["variants"].keys())
print("variants:", names)
dropped = [t for t in pt if (pt[t].get("scope") or {}).get("n", 0) == 0]
if dropped:
    print(f"NOTE: scope answer key empty for {dropped} (no scope-layer items in recent history) — "
          f"excluded from scope-layer comparisons.")
    CLI, MUX, TG = CLI - set(dropped), MUX - set(dropped), TG - set(dropped)
    print(f"effective groups: CLI={sorted(CLI)} MUX={sorted(MUX)} TG={sorted(TG)}")
base = next(n for n in names if "baseline" in n)
issues = next(n for n in names if "issues" in n)
feat = next((n for n in names if "features" in n or "feature" in n), None)
disc = next((n for n in names if "discussion" in n), None)

print("\n=== ISSUES foreign-domain specificity (scope layer) ===")
for v in [issues, feat, base]:
    if not v:
        continue
    i, o = recall(v, CLI), recall(v, MUX)
    print(f"{v:38s} in(cli)={i:.3f} out(mux)={o:.3f} specificity={i-o:+.3f}")
bi, bo = recall(base, CLI), recall(base, MUX)
ii, io_ = recall(issues, CLI), recall(issues, MUX)
bspec, ispec = bi - bo, ii - io_
verdict = ("DEMOTE" if ispec <= bspec + 0.05 else
           "AFFIRM" if ispec >= 2 * bspec else "FLAG (between bounds)")
print(f"-> ISSUES verdict by pre-registered rule: {verdict} "
      f"(issues spec {ispec:+.3f} vs baseline {bspec:+.3f})")

if disc:
    print("\n=== DISCUSSIONS control (telegram targets, scope layer) ===")
    dr, br = runs(disc, TG), runs(base, TG)
    lifts = [a - b for a, b in zip(dr, br)]
    print(f"discussions recall runs: {[round(x,3) for x in dr]}")
    print(f"baseline    recall runs: {[round(x,3) for x in br]}")
    print(f"lift per run: {[round(x,3) for x in lifts]}  mean={sum(lifts)/len(lifts):+.3f}")
    di, do = recall(disc, TG), recall(disc, CLI | MUX)
    bdi, bdo = recall(base, TG), recall(base, CLI | MUX)
    print(f"discussions specificity: in(tg)={di:.3f} out(cli+mux)={do:.3f} -> {di-do:+.3f} "
          f"(baseline: {bdi-bdo:+.3f})")
    ok_lift = sum(lifts) / len(lifts) >= 0.15 and all(x > 0 for x in lifts)
    ok_spec = (di - do) >= (bdi - bdo) + 0.05
    print(f"-> DISCUSSIONS: lift bar {'PASS' if ok_lift else 'FAIL'}, "
          f"specificity bar {'PASS' if ok_spec else 'FAIL'} "
          f"(promotion candidate only if both; n=3 targets, provisional either way)")
