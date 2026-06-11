#!/usr/bin/env -S uv run --python 3.13 --with sentence-transformers --with scikit-learn --with numpy
"""
measure.py — controlled, per-layer measurement of 2080's recall LIFT over a null baseline.

A bare recall number is uninterpretable: a lenient judge against a broad category list "matches"
almost anything (an earlier run scored the supposed-zero 'direction' layer at 0.87). So this measures
recall LIFT = recall(real spine) − recall(NULL spine), with a strict single-best-match judge. Only
lift over a wrong-domain baseline is signal.

Signals (both reported, per layer):
  ML (deterministic):  abstract each answer-key item -> category phrase (abstract_via_fan below),
      embed (all-MiniLM), recall = frac whose max cosine to the spine >= threshold. Null = same vs the
      foreign-domain spine.
  fan (conceptual):    J independent STRICT judges ("name the ONE category this is a DIRECT INSTANCE of,
      or null") via parallel `fan`. hit = majority. Run against real spine AND null spine.

Layers: robustness (vs robustness-axis spine) | scope (vs SCOPE-axis spine). Targets must be OUTSIDE
both spine pools (no leakage). Default: dexto, goose, cline.

Scheduling (2026-06-11): prepare-once-judge-N. Answer keys, layer classification (content-hash
cached), abstraction, and embeddings are computed ONCE; only strict judging repeats — and ALL
repeats × spine variants go into ONE fan batch, so wall-clock ≈ one run regardless of repeats.
Repeats stay independent judge samples (variance is what they measure); variants within a repeat
share the same null sample (interleaving by construction — better controlled than serial runs).

Usage:
  measure.py [--robustness-spine a.json [b.json ...]] [--scope-spine c.json [d.json ...]]
             [--target name=path ...] [--judges 2] [--repeats 1] [--cutoff-frac 0.12] [--json]
Multiple spines per layer = variants compared against the SAME answer keys/null in one process.
Exit codes: 0 OK | 1 USAGE/ERR | 2 NOT_FOUND
"""
from __future__ import annotations
import argparse, hashlib, json, os, pickle, re, subprocess, sys
from pathlib import Path
import numpy as np

from mine_common import fan_batch, extract_json, write_atomic, git_text as git, EXIT_OK, EXIT_NOT_FOUND

# ── embedding + LLM-abstraction substrate (moved here from cluster_fixes.py when it was
# archived 2026-06-11 — measure.py was its last consumer; caches stay path-compatible) ──
CACHE_DIR = Path.home() / ".cache" / "2080-cluster-fixes"
PHRASE_CACHE = CACHE_DIR / "phrases.json"


def _emb_cache_path(model): return CACHE_DIR / f"emb--{model.replace('/', '--')}.pkl"
def _ekey(model, text): return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()[:32]
def _pkey(subj): return hashlib.sha256(subj.encode()).hexdigest()[:32]


def embed(texts, model_name="sentence-transformers/all-MiniLM-L6-v2"):
    p = _emb_cache_path(model_name)
    try:
        cache = pickle.loads(p.read_bytes()) if p.exists() else {}
    except Exception:
        cache = {}
    todo = [t for t in set(texts) if _ekey(model_name, t) not in cache]
    if todo:
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(model_name)
        vecs = m.encode(todo, normalize_embeddings=True, show_progress_bar=False)
        for t, v in zip(todo, vecs):
            cache[_ekey(model_name, t)] = np.asarray(v, dtype="float32")
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(pickle.dumps(cache, protocol=pickle.HIGHEST_PROTOCOL)); os.replace(tmp, p)
    return np.vstack([cache[_ekey(model_name, t)] for t in texts])


def abstract_via_fan(items, model, provider, reasoning, batch_size=32):
    """Commit subject -> short domain-general phrase, content-hash cached. Mutates items."""
    try:
        cache = json.loads(PHRASE_CACHE.read_text()) if PHRASE_CACHE.exists() else {}
    except Exception:
        cache = {}
    max_tokens = max(1500, batch_size * 60)
    todo = [it for it in items if _pkey(it["subject"]) not in cache]
    if todo:
        batches = [todo[i:i + batch_size] for i in range(0, len(todo), batch_size)]
        calls = []
        for bi, batch in enumerate(batches):
            listing = "\n".join(f"{j + 1}. {it['subject'][:160]}" for j, it in enumerate(batch))
            prompt = (
                "For each numbered commit return (a) a SHORT (2-4 word) DOMAIN-GENERAL engineering-category phrase "
                "describing the KIND of work — NO project names/specifics (e.g. 'cost usage telemetry', 'secret "
                "redaction', 'retry on transient failure', 'input validation', 'peer liveness detection'); and "
                "(b) substantive: false if it's churn/chore/vague/filler/version-bump/formatting (not real "
                "engineering work), true otherwise. Return ONLY JSON mapping each number (string) to "
                '{"phrase": "...", "substantive": true|false}.\n\n' + listing
            )
            calls.append({"id": str(bi), "prompt": prompt, "maxTokens": max_tokens})
        print(f"fanning {len(calls)} parallel {model}({reasoning}) calls for {len(todo)} commits…", file=sys.stderr)
        texts = fan_batch(calls, model, provider, reasoning, timeout_ms=120000)
        for bid, text in texts.items():
            if text is None:
                continue
            batch = batches[int(bid)]
            mapping = extract_json(text) or {}
            for j, it in enumerate(batch):
                e = mapping.get(str(j + 1)) or mapping.get(j + 1)
                if isinstance(e, dict) and e.get("phrase"):
                    cache[_pkey(it["subject"])] = {"phrase": str(e["phrase"]).strip().lower(),
                                                   "substantive": bool(e.get("substantive", True))}
                elif isinstance(e, str) and e.strip():
                    cache[_pkey(it["subject"])] = {"phrase": e.strip().lower(), "substantive": True}
        PHRASE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(PHRASE_CACHE, json.dumps(cache))
    for it in items:
        e = cache.get(_pkey(it["subject"]))
        if e:
            it["phrase"] = e["phrase"]; it["substantive"] = e["substantive"]
    return items

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


LAYER_CACHE = CACHE_DIR / "layers.json"
def _lkey(subj): return hashlib.sha256(f"layers-v1\n{subj}".encode()).hexdigest()[:32]


def classify_layers(all_items, model, provider, reasoning):
    """fan-classify every item -> robustness | scope | direction | churn (only robustness/scope
    measured). Content-hash cached: classification is a deterministic property of the item, so
    re-measuring the same targets (every repeat/variant/control re-run) pays zero calls."""
    try:
        lcache = json.loads(LAYER_CACHE.read_text()) if LAYER_CACHE.exists() else {}
    except Exception:
        lcache = {}
    calls, index, CH = [], [], 30
    flat = [(t, i, s) for t, items in all_items.items() for i, s in enumerate(items)
            if _lkey(s) not in lcache]
    if flat:
        print(f"  classifying {len(flat)} uncached items…", file=sys.stderr)
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
    res = fan_batch(calls, model, provider, reasoning) if calls else {}
    for call, chunk in zip(calls, index):
        m = extract_json(res.get(call["id"]) or "") or {}
        for j, (t, i, s) in enumerate(chunk):
            lab = str(m.get(str(j + 1)) or m.get(j + 1) or "churn").lower().strip()
            lcache[_lkey(s)] = lab if lab in ("robustness", "scope", "direction") else "churn"
    if calls:
        LAYER_CACHE.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(LAYER_CACHE, json.dumps(lcache))
    return {t: [lcache.get(_lkey(s), "churn") for s in items] for t, items in all_items.items()}


def judge_calls(target, layer, variant, repeat, items, cats, judges):
    """STRICT single-best-match judge: name the ONE category an item is a direct INSTANCE of, or
    null. One call set per (variant, repeat) — every repeat is an independent judge sample."""
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
            calls.append({"id": f"{target}|{layer}|{variant}|{repeat}|{ci}|{jdg}", "maxTokens": 1100,
                          "prompt": prompt, "_chunk_start": ci, "_n": len(chunk)})
    return calls


def mean_sd(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None, None
    m = sum(xs) / len(xs)
    sd = (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5 if len(xs) > 1 else 0.0
    return round(m, 3), round(sd, 3)


def main():
    ap = argparse.ArgumentParser()
    # default = the sub-type-MATCHED spine (measured: a mismatched spine halves recall, 0.23 vs 0.44);
    # the coordination-sub-type spine lives at checklists/ai-agent-coordination.robustness.json
    ap.add_argument("--robustness-spine", nargs="+", action="extend",
                    help="robustness-axis spine(s); several = variants compared on the same keys "
                         "(default checklists/ai-agent-cli.robustness.json)")
    ap.add_argument("--scope-spine", nargs="+", action="extend",
                    help="SCOPE-axis spine(s); several = variants "
                         "(default checklists/ai-agent-tool.features.json)")
    ap.add_argument("--null-spine", default=None,
                    help="real adjacent-domain spine as the control (e.g. a mined terminal-multiplexer spine); "
                         "falls back to the synthetic 3d-game NULL_SPINE")
    ap.add_argument("--target", action="append", default=[], metavar="name=path")
    ap.add_argument("--judges", type=int, default=2)
    ap.add_argument("--repeats", type=int, default=1,
                    help="independent judge repeats, ALL in one fan batch (≈ same wall-clock as 1)")
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
    layer_paths = {"robustness": a.robustness_spine or ["checklists/ai-agent-cli.robustness.json"],
                   "scope": a.scope_spine or ["checklists/ai-agent-tool.features.json"]}
    # variants[L] = ordered {variant_name: cat_texts}; names must not contain the id separator
    variants = {}
    for L, paths in layer_paths.items():
        variants[L] = {}
        for p in paths:
            if not Path(p).exists():
                print(f"spine not found: {p}", file=sys.stderr); sys.exit(EXIT_NOT_FOUND)
            vname = Path(p).stem.replace("|", "_")
            variants[L][vname] = spine_cat_texts(json.loads(Path(p).read_text()))
    null_cats = spine_cat_texts(null_src)

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
    vecs = {L: {v: (embed([c["embed_text"] for c in cats]) if cats else np.zeros((0, 384)))
                for v, cats in variants[L].items()} for L in LAYERS}
    null_vecs = embed([c["embed_text"] for c in null_cats])
    iv = {s: v for s, v in zip(all_items, embed([phrase_of[s] for s in all_items]))}

    def ml_recall(items, V, t):
        if not items or not len(V):
            return None
        return round(sum(1 for s in items if (iv[s] @ V.T).max() >= t) / len(items), 2)

    # ── fan signal: ONE batch = strict judges × variants × repeats × null (interleaved by
    # construction: every repeat/variant shares identical system conditions) ──
    jcalls = []
    for t in targets:
        for L in LAYERS:
            for r in range(a.repeats):
                for v, cats in variants[L].items():
                    jcalls += judge_calls(t, L, v, r, by_tl[t][L], cats, a.judges)
                jcalls += judge_calls(t, L, "~null", r, by_tl[t][L], null_cats, a.judges)
    print(f"judging (strict, {a.judges} judges × {a.repeats} repeats × "
          f"{ {L: len(variants[L]) for L in LAYERS} } variants + null): {len(jcalls)} calls, one batch…",
          file=sys.stderr)
    jres = fan_batch(jcalls, a.model, a.provider, a.reasoning) if jcalls else {}

    votes = {}  # (t, L, variant, repeat) -> {item_idx: [hit,…]}
    for c in jcalls:
        t, L, v, r, ci, _ = c["id"].split("|")
        m = extract_json(jres.get(c["id"]) or "") or {}
        for k in range(c["_n"]):
            e = m.get(str(k + 1)) or m.get(k + 1) or {}
            cat = e.get("cat") if isinstance(e, dict) else e
            hit = bool(cat) and str(cat).lower() not in ("null", "none", "")
            votes.setdefault((t, L, v, int(r)), {}).setdefault(int(ci) + k, []).append(hit)

    def llm_recall(t, L, v, r):
        vt = votes.get((t, L, v, r), {})
        n = len(by_tl[t][L])
        if n == 0:
            return None
        hits = sum(1 for idx in range(n) if sum(vt.get(idx, [])) * 2 > len(vt.get(idx, [1])))
        return round(hits / n, 2)

    def lift(real, null):
        return None if real is None or null is None else round(real - null, 2)

    # ── report: per layer × variant, per-repeat lifts + mean/sd across repeats ──
    rep = {"targets": list(targets), "judges": a.judges, "repeats": a.repeats,
           "ml_threshold": HEADLINE_T, "control": f"null spine = {null_desc}",
           "spines": {L: dict(zip(variants[L], layer_paths[L])) for L in LAYERS},
           "per_target": {}, "aggregate": {}}
    for t in targets:
        rep["per_target"][t] = {}
        for L in LAYERS:
            items = by_tl[t][L]
            rep["per_target"][t][L] = {"n": len(items), "variants": {}}
            for v in variants[L]:
                ml_real = ml_recall(items, vecs[L][v], HEADLINE_T)
                ml_null = ml_recall(items, null_vecs, HEADLINE_T)
                runs = []
                for r in range(a.repeats):
                    lr, ln = llm_recall(t, L, v, r), llm_recall(t, L, "~null", r)
                    runs.append({"llm_real": lr, "llm_null": ln, "llm_lift": lift(lr, ln)})
                rep["per_target"][t][L]["variants"][v] = {
                    "ml_real": ml_real, "ml_null": ml_null, "ml_lift": lift(ml_real, ml_null),
                    "llm_runs": runs}

    for L in LAYERS:
        rep["aggregate"][L] = {"n_total": sum(rep["per_target"][t][L]["n"] for t in targets),
                               "variants": {}}
        for v in variants[L]:
            per_run_lifts, per_run_real, per_run_null = [], [], []
            for r in range(a.repeats):
                lifts = [rep["per_target"][t][L]["variants"][v]["llm_runs"][r]["llm_lift"] for t in targets]
                reals = [rep["per_target"][t][L]["variants"][v]["llm_runs"][r]["llm_real"] for t in targets]
                nulls = [rep["per_target"][t][L]["variants"][v]["llm_runs"][r]["llm_null"] for t in targets]
                per_run_lifts.append(mean_sd(lifts)[0]); per_run_real.append(mean_sd(reals)[0])
                per_run_null.append(mean_sd(nulls)[0])
            lm, lsd = mean_sd(per_run_lifts)
            rep["aggregate"][L]["variants"][v] = {
                "ml_lift": mean_sd([rep["per_target"][t][L]["variants"][v]["ml_lift"] for t in targets])[0],
                "llm_lift_runs": per_run_lifts, "llm_lift_mean": lm, "llm_lift_sd": lsd,
                "llm_real_mean": mean_sd(per_run_real)[0], "llm_null_mean": mean_sd(per_run_null)[0]}

    if a.json:
        print(json.dumps(rep, indent=2)); sys.exit(EXIT_OK)

    print(f"\n=== 2080 RECALL LIFT over null baseline (strict {a.judges}-judge fan × {a.repeats} repeats + ML) ===")
    print(f"targets: {', '.join(targets)} | null = {null_desc} | ML @ {HEADLINE_T}\n")
    hdr = f"{'layer':<11}{'variant':<34}{'n':>4} | {'lift runs':<22}{'mean±sd':>13} | {'real':>5}{'null':>6}{'mlΔ':>7}"
    print(hdr); print("-" * len(hdr))
    for L in LAYERS:
        g = rep["aggregate"][L]
        for v, d in g["variants"].items():
            runs = " ".join(f"{x:+.2f}" if x is not None else "?" for x in d["llm_lift_runs"])
            ms = f"{d['llm_lift_mean']:+.3f}±{d['llm_lift_sd']:.3f}" if d["llm_lift_mean"] is not None else "?"
            print(f"{L:<11}{v:<34}{g['n_total']:>4} | {runs:<22}{ms:>13} | "
                  f"{str(d['llm_real_mean']):>5}{str(d['llm_null_mean']):>6}{str(d['ml_lift']):>7}")
    print("\nLIFT = real − null. Only lift is signal; raw recall conflates real matching with judge leniency.")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
