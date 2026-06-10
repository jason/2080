#!/usr/bin/env -S uv run --python 3.13 --with sentence-transformers --with scikit-learn --with numpy
"""
measure.py — controlled, per-layer measurement of 2080's recall LIFT over a null baseline.

A bare recall number is uninterpretable: a lenient judge against a broad category list "matches"
almost anything (an earlier run scored the supposed-zero 'direction' layer at 0.87). So this measures
recall LIFT = recall(real spine) − recall(NULL spine), with a strict single-best-match judge. Only
lift over a wrong-domain baseline is signal.

Signals (both reported, per layer):
  ML (deterministic):  abstract each answer-key item -> category phrase (cluster_fixes.abstract_via_fan),
      embed (all-MiniLM), recall = frac whose max cosine to the spine >= threshold. Null = same vs the
      foreign-domain spine.
  fan (conceptual):    J independent STRICT judges ("name the ONE category this is a DIRECT INSTANCE of,
      or null") via parallel `fan`. hit = majority. Run against real spine AND null spine.

Layers: robustness (vs cluster_fixes spine) | scope (vs feature_mine spine). Targets must be OUTSIDE
both spine pools (no leakage). Default: dexto, goose, cline.

Usage:
  measure.py [--robustness-spine a.json] [--scope-spine b.json] [--target name=path ...]
             [--judges 2] [--cutoff-frac 0.12] [--json]
Exit codes: 0 OK | 1 USAGE/ERR | 2 NOT_FOUND
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from pathlib import Path
import numpy as np

from mine_common import fan_batch, extract_json, EXIT_OK, EXIT_NOT_FOUND
from cluster_fixes import embed, abstract_via_fan

THRESHOLDS = [0.35, 0.40, 0.45, 0.50, 0.55]
HEADLINE_T = 0.45
LAYERS = ("robustness", "scope")

# Foreign-domain NULL spine: real engineering categories from 3d-game/graphics — disjoint from
# AI-agent tools. If the real spine doesn't beat THIS, "recall" was just matcher leniency.
NULL_SPINE = {"required": [{"category": c} for c in [
    "physics collision response", "camera occlusion handling", "texture LOD streaming",
    "skeletal animation blending", "frustum culling", "save-game serialization",
    "input remapping and deadzones", "navmesh pathfinding", "particle system pooling",
    "audio spatialization", "shader hot-reload", "level-of-detail mesh swapping",
    "gamepad rumble feedback", "sprite atlas packing", "screen-space reflections",
    "tilemap chunk loading", "dialogue tree branching", "inventory grid management",
    "ragdoll death physics", "minimap fog of war"]], "optional": []}


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True).stdout


def answer_key(repo, cutoff_frac=0.12, cap=130):
    """Whole second-85%: cutoff at an early MATURITY FRACTION, then feat/fix across all later history,
    EVENLY SAMPLED to `cap` so the key spans the feature era, not just the immediate post-demo window."""
    shas = git(repo, "rev-list", "--reverse", "HEAD").split()
    cut = shas[min(len(shas) - 1, max(40, int(len(shas) * cutoff_frac)))]
    later = git(repo, "log", "--reverse", "--format=%s", f"{cut}..HEAD").splitlines()
    keep, seen = [], set()
    for s in later:
        if re.match(r"^(feat|fix|perf|security)", s, re.I):
            c = re.sub(r"\s*\(#\d+\)\s*$", "", s).strip()
            k = c.lower()
            if k not in seen and len(c) > 8:
                seen.add(k)
                keep.append(c)
    if len(keep) > cap:
        keep = [keep[round(i * (len(keep) - 1) / (cap - 1))] for i in range(cap)]
    return keep


def spine_cat_texts(spine):
    out = []
    for c in spine.get("required", []) + spine.get("optional", []):
        label = c.get("category", "")
        embed_text = " ".join(x for x in (label, c.get("aliases", ""), c.get("what", "")) if x) or label
        out.append({"label": label, "embed_text": embed_text})
    return out


def classify_layers(all_items, model, provider, reasoning):
    """fan-classify every item -> robustness | scope | direction | churn (only robustness/scope measured)."""
    calls, index, CH = [], [], 30
    flat = [(t, i, s) for t, items in all_items.items() for i, s in enumerate(items)]
    for ci in range(0, len(flat), CH):
        chunk = flat[ci:ci + CH]
        listing = "\n".join(f"{j+1}. {s}" for j, (_, _, s) in enumerate(chunk))
        calls.append({"id": f"c{ci}", "maxTokens": 1500, "prompt":
            "Classify each later commit from an AI-agent tool into exactly one layer:\n"
            "- robustness: hardening/edge-cases/NFR/operability of EXISTING capability (errors, retries, "
            "persistence correctness, cost/usage tracking, packaging, perf, auth-hardening).\n"
            "- scope: a NEW generic product capability a mature tool of this kind converges on (multi-provider, "
            "web UI, plugin/tool system, auth flow, CI integration, reporting).\n"
            "- direction: a project-SPECIFIC product bet not generic to the category.\n"
            "- churn: docs/CI/refactor/version-bump, no user-facing change.\n\n"
            f"COMMITS:\n{listing}\n\nReturn ONLY JSON {{number: \"robustness|scope|direction|churn\"}}."})
        index.append(chunk)
    res = fan_batch(calls, model, provider, reasoning)
    tagged = {t: [None] * len(items) for t, items in all_items.items()}
    for call, chunk in zip(calls, index):
        m = extract_json(res.get(call["id"]) or "") or {}
        for j, (t, i, _) in enumerate(chunk):
            lab = str(m.get(str(j + 1)) or m.get(j + 1) or "churn").lower().strip()
            tagged[t][i] = lab if lab in ("robustness", "scope", "direction") else "churn"
    return tagged


def judge_calls(target, layer, spine_id, items, cats, judges):
    """STRICT single-best-match judge: name the ONE category an item is a direct INSTANCE of, or null."""
    calls, CH = [], 18
    cat_listing = "\n".join(f"- {c['label']}" for c in cats)
    for ci in range(0, len(items), CH):
        chunk = items[ci:ci + CH]
        listing = "\n".join(f"{j+1}. {s}" for j, s in enumerate(chunk))
        prompt = (f"PREDICTED categories:\n{cat_listing}\n\n"
                  f"LATER-WORK items a software project actually shipped:\n{listing}\n\n"
                  "For each item, name the SINGLE category above that the item is a DIRECT INSTANCE OF "
                  "(the work is literally an example of that category). If it only loosely or thematically "
                  "relates, or matches none, return null. Be STRICT — when unsure, return null. "
                  'Return ONLY JSON {number: {"cat": "<exact category label or null>"}}.')
        for jdg in range(judges):
            calls.append({"id": f"{target}|{layer}|{spine_id}|{ci}|{jdg}", "maxTokens": 1100,
                          "prompt": prompt, "_chunk_start": ci, "_n": len(chunk)})
    return calls


def main():
    ap = argparse.ArgumentParser()
    # default = the sub-type-MATCHED spine (measured: a mismatched spine halves recall, 0.23 vs 0.44);
    # the coordination-sub-type spine lives at checklists/ai-agent-coordination.robustness.json
    ap.add_argument("--robustness-spine", default="checklists/ai-agent-cli.robustness.json")
    ap.add_argument("--scope-spine", default="checklists/ai-agent-tool.features.json")
    ap.add_argument("--null-spine", default=None,
                    help="real adjacent-domain spine as the control (e.g. a mined terminal-multiplexer spine); "
                         "falls back to the synthetic 3d-game NULL_SPINE")
    ap.add_argument("--target", action="append", default=[], metavar="name=path")
    ap.add_argument("--judges", type=int, default=2)
    ap.add_argument("--cutoff-frac", type=float, default=0.12)
    ap.add_argument("--model", default="gpt-5.5")
    ap.add_argument("--provider", default="openai-codex")
    ap.add_argument("--reasoning", default="low")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not a.target:
        a.target = ["dexto=/tmp/dexto-bt", "goose=/tmp/goose-bt", "cline=/tmp/cline-bt"]
    targets = {}
    for spec in a.target:
        name, _, path = spec.partition("=")
        if not Path(path).exists():
            print(f"target not found: {path}", file=sys.stderr); sys.exit(EXIT_NOT_FOUND)
        targets[name] = path

    null_src = json.loads(Path(a.null_spine).read_text()) if a.null_spine else NULL_SPINE
    null_desc = f"mined spine {a.null_spine}" if a.null_spine else "synthetic 3d-game/graphics categories"
    spines = {
        "robustness": spine_cat_texts(json.loads(Path(a.robustness_spine).read_text())),
        "scope": spine_cat_texts(json.loads(Path(a.scope_spine).read_text())),
        "null": spine_cat_texts(null_src),
    }

    # ── answer keys + layer classification ──
    print("building answer keys…", file=sys.stderr)
    raw = {name: answer_key(path, cutoff_frac=a.cutoff_frac) for name, path in targets.items()}
    print(f"  {{ {', '.join(f'{k}:{len(v)}' for k,v in raw.items())} }} items; classifying via fan…", file=sys.stderr)
    tagged = classify_layers(raw, a.model, a.provider, a.reasoning)
    by_tl = {t: {L: [] for L in LAYERS} for t in targets}
    for t in targets:
        for s, lab in zip(raw[t], tagged[t]):
            if lab in by_tl[t]:
                by_tl[t][lab].append(s)

    # ── ML signal: abstract items -> phrases, embed, recall vs real-layer spine AND null spine ──
    all_items = sorted({s for t in targets for s in raw[t]})
    print(f"abstracting {len(all_items)} items to phrases via fan (for ML)…", file=sys.stderr)
    ab = [{"subject": s} for s in all_items]
    abstract_via_fan(ab, a.model, a.provider, a.reasoning)
    phrase_of = {it["subject"]: it.get("phrase") or it["subject"] for it in ab}
    print("embedding (all-MiniLM)…", file=sys.stderr)
    vecs = {k: (embed([c["embed_text"] for c in cats]) if cats else np.zeros((0, 384))) for k, cats in spines.items()}
    iv = {s: v for s, v in zip(all_items, embed([phrase_of[s] for s in all_items]))}

    def ml_recall(items, V, t):
        if not items or not len(V):
            return None
        return round(sum(1 for s in items if (iv[s] @ V.T).max() >= t) / len(items), 2)

    # ── fan signal: STRICT judges vs real spine AND null spine, per layer ──
    print(f"judging (strict, {a.judges} judges) vs real + null spine via fan…", file=sys.stderr)
    jcalls = []
    for t in targets:
        for L in LAYERS:
            jcalls += judge_calls(t, L, "real", by_tl[t][L], spines[L], a.judges)
            jcalls += judge_calls(t, L, "null", by_tl[t][L], spines["null"], a.judges)
    jres = fan_batch(jcalls, a.model, a.provider, a.reasoning) if jcalls else {}

    votes = {t: {L: {"real": {}, "null": {}} for L in LAYERS} for t in targets}
    for c in jcalls:
        t, layer, spine_id, ci, _ = c["id"].split("|")
        ci = int(ci)
        m = extract_json(jres.get(c["id"]) or "") or {}
        for k in range(c["_n"]):
            e = m.get(str(k + 1)) or m.get(k + 1) or {}
            cat = e.get("cat") if isinstance(e, dict) else e
            hit = bool(cat) and str(cat).lower() not in ("null", "none", "")
            votes[t][layer][spine_id].setdefault(ci + k, []).append(hit)

    def llm_recall(t, L, spine_id):
        v = votes[t][L][spine_id]
        n = len(by_tl[t][L])
        if n == 0:
            return None
        hits = sum(1 for idx in range(n) if sum(v.get(idx, [])) * 2 > len(v.get(idx, [1])))
        return round(hits / n, 2)

    def lift(real, null):
        return None if real is None or null is None else round(real - null, 2)

    # ── report ──
    rep = {"targets": list(targets), "judges": a.judges, "ml_threshold": HEADLINE_T,
           "control": f"null spine = {null_desc}",
           "robustness_spine": a.robustness_spine, "scope_spine": a.scope_spine, "per_target": {}}
    for t in targets:
        rep["per_target"][t] = {}
        for L in LAYERS:
            items = by_tl[t][L]
            ml_real = ml_recall(items, vecs[L], HEADLINE_T)
            ml_null = ml_recall(items, vecs["null"], HEADLINE_T)
            llm_real = llm_recall(t, L, "real")
            llm_null = llm_recall(t, L, "null")
            rep["per_target"][t][L] = {"n": len(items),
                                       "ml_real": ml_real, "ml_null": ml_null, "ml_lift": lift(ml_real, ml_null),
                                       "llm_real": llm_real, "llm_null": llm_null, "llm_lift": lift(llm_real, llm_null)}

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 2) if xs else None

    rep["aggregate"] = {L: {
        "n_total": sum(rep["per_target"][t][L]["n"] for t in targets),
        "ml_real": mean([rep["per_target"][t][L]["ml_real"] for t in targets]),
        "ml_null": mean([rep["per_target"][t][L]["ml_null"] for t in targets]),
        "ml_lift": mean([rep["per_target"][t][L]["ml_lift"] for t in targets]),
        "llm_real": mean([rep["per_target"][t][L]["llm_real"] for t in targets]),
        "llm_null": mean([rep["per_target"][t][L]["llm_null"] for t in targets]),
        "llm_lift": mean([rep["per_target"][t][L]["llm_lift"] for t in targets]),
    } for L in LAYERS}

    if a.json:
        print(json.dumps(rep, indent=2)); sys.exit(EXIT_OK)

    print(f"\n=== 2080 RECALL LIFT over null baseline (strict {a.judges}-judge fan + ML) ===")
    print(f"targets: {', '.join(targets)} | null = 3d-game categories | ML @ {HEADLINE_T}\n")
    hdr = f"{'target':<9}{'layer':<11}{'n':>4} | {'llm_real':>8}{'llm_null':>9}{'llm_LIFT':>9} | {'ml_real':>7}{'ml_null':>8}{'ml_LIFT':>8}"
    print(hdr); print("-" * len(hdr))
    for t in targets:
        for L in LAYERS:
            d = rep["per_target"][t][L]
            print(f"{t:<9}{L:<11}{d['n']:>4} | {str(d['llm_real']):>8}{str(d['llm_null']):>9}{str(d['llm_lift']):>9} | "
                  f"{str(d['ml_real']):>7}{str(d['ml_null']):>8}{str(d['ml_lift']):>8}")
    print("-" * len(hdr))
    for L in LAYERS:
        g = rep["aggregate"][L]
        print(f"{'MEAN':<9}{L:<11}{g['n_total']:>4} | {str(g['llm_real']):>8}{str(g['llm_null']):>9}{str(g['llm_lift']):>9} | "
              f"{str(g['ml_real']):>7}{str(g['ml_null']):>8}{str(g['ml_lift']):>8}")
    print("\nLIFT = real − null. Only lift is signal; raw recall conflates real matching with judge leniency.")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
