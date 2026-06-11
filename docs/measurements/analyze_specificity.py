#!/usr/bin/env python3
"""Split the specificity-control measure.py output into in-domain vs out-of-domain recall."""
import json

d = json.load(open("/tmp/specificity-control.json"))
IN, OUT = {"dexto", "goose", "cline"}, {"astrbot", "langbot", "tgbot"}
pt = d["per_target"]
print("targets present:", sorted(pt.keys()))

for layer in ("scope", "robustness"):
    print(f"--- {layer} ---")
    variants = {}
    for tgt, td in pt.items():
        ld = td.get(layer) or {}
        for v, vd in (ld.get("variants") or {}).items():
            variants.setdefault(v, {})[tgt] = vd

    def mean(per, keys):
        vals = []
        for t in keys:
            if t in per and per[t].get("llm_runs"):
                runs = [r["llm_real"] for r in per[t]["llm_runs"]]
                vals.append(sum(runs) / len(runs))
        return sum(vals) / len(vals) if vals else None

    for v, per in variants.items():
        ri, ro = mean(per, IN), mean(per, OUT)
        if ri is None:
            continue
        spec = None if ro is None else ri - ro
        fmt = lambda x: "n/a" if x is None else f"{x:.3f}"
        print(f"{v:40s} in={fmt(ri)} out={fmt(ro)} specificity={fmt(spec)}")
        for t in sorted(per):
            runs = [r["llm_real"] for r in per[t].get("llm_runs", [])]
            if runs:
                tag = "IN " if t in IN else "OUT"
                print(f"    {tag} {t:10s} {sum(runs)/len(runs):.3f}  (n={per[t].get('n', d['per_target'][t][layer]['n'])})")
