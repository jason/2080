#!/usr/bin/env -S uv run --python 3.13 --with sentence-transformers --with scikit-learn --with numpy
"""
cluster_fixes.py — 2080's MEASURED category backbone (LLM-abstraction + ML clustering hybrid).

Naive embed-the-raw-commit clustering failed: it grouped by project vocabulary ("rally", "feat")
and dumped ~88% as noise. The fix is a hybrid:
  1. LLM (gpt-5.5 low, fanned out in parallel via `fan`) abstracts each commit -> a short,
     DOMAIN-GENERAL category phrase, stripped of project specifics.  ← the LLM's real strength
  2. Embed + DBSCAN/cosine cluster those phrases (tight semantic space, no project noise).  ← ML
  3. Measure cross-project recurrence: fraction of clusters spanning >=2 projects.  ← reproducible

Reuses the embedding+cache pattern from ~/projects/tools/corrections/cluster_embedding.py
and the `fan` parallel-LLM CLI for the abstraction pass.

Usage:
  cluster_fixes.py <harvest1.json> ... [--model gpt-5.5] [--provider openai] [--reasoning low]
                   [--eps E] [--min-samples N] [--no-abstract] [--json]
Exit codes: 0 OK | 1 USAGE/ERR | 2 NOT_FOUND | 3 EMPTY
"""
from __future__ import annotations
import argparse, hashlib, json, os, pickle, re, subprocess, sys
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "2080-cluster-fixes"
PHRASE_CACHE = CACHE_DIR / "phrases.json"
EXIT_OK, EXIT_ERR, EXIT_NOT_FOUND, EXIT_EMPTY = 0, 1, 2, 3

PROJECT_FIXUP = {"bl-harvest": "build-loop", "va-harvest": "voltagent", "sym-harvest": "symphony", "dexto-": "dexto"}


def norm_project(name):
    for pre, clean in PROJECT_FIXUP.items():
        if name.startswith(pre):
            return clean
    return name


def load_items(files):
    items = []
    for f in files:
        p = Path(f)
        if not p.exists():
            print(f"not found: {f}", file=sys.stderr); sys.exit(EXIT_NOT_FOUND)
        d = json.loads(p.read_text())
        proj = norm_project(d.get("project", p.stem))
        for c in d.get("commits", []):
            subj = (c.get("subject", "") or "").strip()
            if len(subj) < 6:
                continue
            items.append({"project": proj, "sha": c.get("sha", ""), "subject": subj})
    return items


# ── embedding cache (reused pattern) ──
def _emb_cache_path(model): return CACHE_DIR / f"emb--{model.replace('/', '--')}.pkl"
def _load_emb(model):
    p = _emb_cache_path(model)
    try: return pickle.loads(p.read_bytes()) if p.exists() else {}
    except Exception: return {}
def _save_emb(model, cache):
    p = _emb_cache_path(model); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp"); tmp.write_bytes(pickle.dumps(cache, protocol=pickle.HIGHEST_PROTOCOL)); os.replace(tmp, p)
def _ekey(model, text): return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()[:32]


def embed(texts, model_name="sentence-transformers/all-MiniLM-L6-v2"):
    import numpy as np
    cache = _load_emb(model_name)
    todo = [t for t in set(texts) if _ekey(model_name, t) not in cache]
    if todo:
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(model_name)
        vecs = m.encode(todo, normalize_embeddings=True, show_progress_bar=False)
        for t, v in zip(todo, vecs):
            cache[_ekey(model_name, t)] = np.asarray(v, dtype="float32")
        _save_emb(model_name, cache)
    return np.vstack([cache[_ekey(model_name, t)] for t in texts])


# ── LLM abstraction via fan (parallel) ──
def _pkey(subj): return hashlib.sha256(subj.encode()).hexdigest()[:32]
def _load_phrases():
    try: return json.loads(PHRASE_CACHE.read_text()) if PHRASE_CACHE.exists() else {}
    except Exception: return {}
def _save_phrases(d):
    PHRASE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    PHRASE_CACHE.write_text(json.dumps(d))


def _extract_json_obj(text):
    try: return json.loads(text)
    except Exception: pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try: return json.loads(m.group(0))
        except Exception: return {}
    return {}


def abstract_via_fan(items, model, provider, reasoning, batch_size=32):
    cache = _load_phrases()
    max_tokens = max(1500, batch_size * 60)  # scale output budget to batch so big batches don't truncate
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
            calls.append({"id": str(bi), "provider": provider, "model": model, "reasoning": reasoning,
                          "prompt": prompt, "maxTokens": max_tokens, "timeoutMs": 120000})
        print(f"fanning {len(calls)} parallel {model}({reasoning}) calls for {len(todo)} commits…", file=sys.stderr)
        r = subprocess.run(["fan"], input=json.dumps({"calls": calls}), capture_output=True, text=True, timeout=600)
        if not r.stdout:
            print(f"fan failed: {r.stderr[:400]}", file=sys.stderr); sys.exit(EXIT_ERR)
        results = json.loads(r.stdout).get("results", [])
        ok = 0
        for res in results:
            if not res.get("ok"):
                continue
            bi = int(res["id"]); batch = batches[bi]
            mapping = _extract_json_obj(res.get("text", ""))
            for j, it in enumerate(batch):
                e = mapping.get(str(j + 1)) or mapping.get(j + 1)
                if isinstance(e, dict) and e.get("phrase"):
                    cache[_pkey(it["subject"])] = {"phrase": str(e["phrase"]).strip().lower(),
                                                   "substantive": bool(e.get("substantive", True))}; ok += 1
                elif isinstance(e, str) and e.strip():
                    cache[_pkey(it["subject"])] = {"phrase": e.strip().lower(), "substantive": True}; ok += 1
        _save_phrases(cache)
        print(f"  abstracted {ok}/{len(todo)} (fan results ok: {sum(1 for x in results if x.get('ok'))}/{len(results)})", file=sys.stderr)
    for it in items:
        c = cache.get(_pkey(it["subject"]))
        if isinstance(c, dict):
            it["phrase"], it["substantive"] = c.get("phrase", it["subject"][:40].lower()), c.get("substantive", True)
        elif isinstance(c, str):  # legacy phrase-only cache entry
            it["phrase"], it["substantive"] = c, True
        else:
            it["phrase"], it["substantive"] = it["subject"][:40].lower(), True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--model", default="gpt-5.5")
    ap.add_argument("--provider", default="openai-codex")
    ap.add_argument("--reasoning", default="low")
    ap.add_argument("--eps", type=float, default=0.34)  # tuned: knee — max distinct clusters, no catch-all merge
    ap.add_argument("--min-samples", type=int, default=2)
    ap.add_argument("--batch", type=int, default=32, help="commits per fan call (≤~50; sweet spot 32-40)")
    ap.add_argument("--sweep", action="store_true", help="grid-sweep eps × min_samples and print metrics")
    ap.add_argument("--emit-checklist", metavar="PATH", help="write a scoped, tiered second-85% checklist")
    ap.add_argument("--app-type", default="ai-agent-tool", help="scope label for the emitted checklist")
    ap.add_argument("--no-abstract", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not a.files:
        cap = {"tool": "cluster_fixes", "version": "0.2",
               "args": "<harvest.json>... [--model][--provider][--reasoning][--eps][--min-samples][--no-abstract][--json]",
               "exit_codes": {"0": "ok", "1": "usage/err", "2": "not_found", "3": "empty"}}
        if a.json: print(json.dumps(cap)); sys.exit(EXIT_OK)
        print(cap["args"], file=sys.stderr); sys.exit(EXIT_ERR)

    items = load_items(a.files)
    if not items:
        print("no commits", file=sys.stderr); sys.exit(EXIT_EMPTY)

    if a.no_abstract:
        texts = [it["subject"] for it in items]
        for it in items: it["phrase"] = it["subject"]
    else:
        abstract_via_fan(items, a.model, a.provider, a.reasoning, a.batch)
        slop = [it for it in items if not it.get("substantive", True)]
        if slop:
            print(f"dropped {len(slop)} non-substantive (slop/churn) commits before clustering", file=sys.stderr)
        items = [it for it in items if it.get("substantive", True)]
        texts = [it["phrase"] for it in items]

    V = embed(texts)
    from sklearn.cluster import DBSCAN
    from collections import Counter, defaultdict

    if a.sweep:
        import numpy as np
        from sklearn.metrics import silhouette_score
        print(f"{'eps':>5} {'ms':>3} {'clusters':>8} {'noise%':>7} {'recurClust':>10} {'recurCommit%':>12} {'maxClust':>8} {'silhouette':>10}")
        for eps in (0.22, 0.26, 0.30, 0.34, 0.38, 0.42, 0.46):
            for ms in (2, 3):
                lab = DBSCAN(eps=eps, min_samples=ms, metric="cosine").fit_predict(V)
                mask = lab != -1
                cl = defaultdict(list)
                for it, l in zip(items, lab):
                    if l != -1:
                        cl[l].append(it)
                nclust = len(cl)
                multi = [c for c in cl.values() if len({m["project"] for m in c}) >= 2]
                tot = int(mask.sum())
                recur_commit = 100 * sum(len(c) for c in multi) / max(1, tot)
                maxc = max((len(c) for c in cl.values()), default=0)
                try:
                    sil = silhouette_score(V[mask], lab[mask], metric="cosine") if nclust >= 2 and tot > nclust else float("nan")
                except Exception:
                    sil = float("nan")
                print(f"{eps:>5} {ms:>3} {nclust:>8} {100*(~mask).sum()/len(lab):>6.1f} {len(multi):>10} {recur_commit:>11.1f} {maxc:>8} {sil:>10.3f}")
        sys.exit(EXIT_OK)

    labels = DBSCAN(eps=a.eps, min_samples=a.min_samples, metric="cosine").fit_predict(V)

    clusters = defaultdict(list)
    for it, lab in zip(items, labels):
        clusters[int(lab)].append(it)
    noise = clusters.pop(-1, [])
    projects = sorted(set(it["project"] for it in items))

    info, multi = [], 0
    for lab, members in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        projs = Counter(m["project"] for m in members)
        is_multi = len(projs) >= 2
        multi += int(is_multi)
        common = Counter(m["phrase"] for m in members).most_common(3)
        info.append({"label": " / ".join(p for p, _ in common), "size": len(members),
                     "projects": dict(projs), "multi_project": is_multi})

    total_clustered = sum(len(m) for m in clusters.values())
    commits_multi = sum(c["size"] for c in info if c["multi_project"])
    report = {
        "abstraction": (None if a.no_abstract else f"{a.model}/{a.reasoning} via fan"),
        "projects": projects, "n_commits": len(items), "n_clusters": len(clusters),
        "noise_pct": round(100 * len(noise) / len(items), 1),
        "recurring_clusters": multi,
        "recurring_cluster_pct": round(100 * multi / max(1, len(clusters)), 1),
        "commits_in_recurring_clusters_pct": round(100 * commits_multi / max(1, total_clustered), 1),
        "clusters": info,
    }
    if a.emit_checklist:
        cats = [{"category": c["label"].split(" / ")[0], "aliases": c["label"],
                 "tier": "required" if c["multi_project"] else "optional",
                 "projects": list(c["projects"].keys()), "recurrence_projects": len(c["projects"]), "size": c["size"]}
                for c in info]
        listing = "\n".join(f"{i + 1}. {c['aliases']}" for i, c in enumerate(cats))
        prompt = ("For each numbered engineering category, write ONE concrete DAY-1 CHECK — a specific test or "
                  "inspection that reveals whether a project covers it (e.g. 'feed the parser a NUL byte + an "
                  "oversized line; confirm it rejects/quotes instead of panicking'). Return ONLY JSON "
                  "{number: check}.\n\n" + listing)
        r = subprocess.run(["fan"], input=json.dumps({"calls": [{"id": "0", "provider": a.provider, "model": a.model,
                            "reasoning": a.reasoning, "prompt": prompt, "maxTokens": max(2000, len(cats) * 60),
                            "timeoutMs": 120000}]}), capture_output=True, text=True, timeout=300)
        tells = {}
        try:
            res = json.loads(r.stdout)["results"][0]
            if res.get("ok"):
                tells = _extract_json_obj(res.get("text", ""))
        except Exception:
            pass
        for i, c in enumerate(cats):
            c["day1_tell"] = str(tells.get(str(i + 1)) or tells.get(i + 1) or "").strip()
        checklist = {
            "app_type": a.app_type,
            "scope_note": f"Derived ONLY from {a.app_type} repos {report['projects']}. Categories are app-type-relative — "
                          f"this checklist does NOT transfer to other app types.",
            "derived_from": report["projects"],
            "commit_weighted_recurrence_pct": report["commits_in_recurring_clusters_pct"],
            "required": [c for c in cats if c["tier"] == "required"],
            "optional": [c for c in cats if c["tier"] == "optional"],
        }
        Path(a.emit_checklist).write_text(json.dumps(checklist, indent=2))
        print(f"\n→ {a.app_type} checklist: {len(checklist['required'])} required (recurring) + "
              f"{len(checklist['optional'])} optional (project-specific) → {a.emit_checklist}", file=sys.stderr)

    if a.json:
        print(json.dumps(report, indent=2)); sys.exit(EXIT_OK)

    print(f"abstraction: {report['abstraction']}  | eps={a.eps} min_samples={a.min_samples}")
    print(f"projects: {projects}")
    print(f"{len(items)} commits → {len(clusters)} clusters, {report['noise_pct']}% noise")
    print(f"\nMEASURED RECURRENCE: {multi}/{len(clusters)} clusters span ≥2 projects "
          f"({report['recurring_cluster_pct']}%); {report['commits_in_recurring_clusters_pct']}% of "
          f"clustered commits sit in recurring clusters\n")
    for c in info:
        tag = "🔁" if c["multi_project"] else "· "
        print(f"{tag} [{c['size']:>2}] {c['label']}   {c['projects']}")
    sys.exit(EXIT_OK)


main()
