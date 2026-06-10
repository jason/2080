"""
mine_common.py — shared substrate for 2080's mining tools (the "mine family").

2080 mines neighbor history along multiple AXES (lenses): recurring-fix → robustness spine
(`cluster_fixes.py`), feature-surface → scope spine (`feature_mine.py`), and future dimensions
(integration-surface, threat-surface, operability-surface, …). Every lens shares the same shape:
read a source, abstract through an LLM, aggregate across neighbors. This module is the shared
LLM-call + JSON-extraction substrate so each new lens is a config, not new plumbing.

Reuses the `fan` parallel-LLM CLI (gpt-5.5-low via Codex OAuth) — the 2080-standard surface.
"""
from __future__ import annotations
import json, os, re, subprocess, time

EXIT_OK, EXIT_ERR, EXIT_NOT_FOUND, EXIT_EMPTY = 0, 1, 2, 3

# fan has NO internal retry: a transient 429 becomes ok:false, which downstream means a silently
# missing judge vote / assessment. Concurrency and retries are therefore coupled knobs: raising
# concurrency without retries trades wall-time for data corruption.
# Probed 2026-06-10 (openai-codex): 100% ok at 8/12/16/24-wide trivial bursts AND 32 realistic
# long-generation calls at 16-wide (25.5s wall vs ~100s at 4-wide). Default 16 + 1 retry as the
# safety net; re-probe if the provider or account tier changes.
FAN_CONCURRENCY = int(os.environ.get("FAN_CONCURRENCY", "16"))
FAN_RETRIES = int(os.environ.get("FAN_RETRIES", "1"))


def extract_json(text):
    """Tolerant JSON extraction: whole string, then first {...} / [...] span."""
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"[\{\[][\s\S]*[\}\]]", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def _fan_once(calls, model, provider, reasoning, timeout_ms, concurrency):
    cfg = {"maxConcurrency": max(1, concurrency),
           "calls": [{"id": str(c["id"]), "provider": provider, "model": model, "reasoning": reasoning,
                      "prompt": c["prompt"], "maxTokens": c.get("maxTokens", 3000), "timeoutMs": timeout_ms}
                     for c in calls]}
    r = subprocess.run(["fan"], input=json.dumps(cfg), capture_output=True, text=True,
                       timeout=timeout_ms / 1000 + 120)
    if not r.stdout:
        raise RuntimeError(f"fan failed: {(r.stderr or '')[:300]}")
    out = {}
    for res in json.loads(r.stdout).get("results", []):
        out[str(res.get("id"))] = res.get("text", "") if res.get("ok") else None
    return out


def fan_batch(calls, model="gpt-5.5", provider="openai-codex", reasoning="low", timeout_ms=180000,
              concurrency=None, retries=None):
    """Run N prompts through one `fan` invocation (fan fans them out concurrently).
    `calls` = [{"id": str, "prompt": str, "maxTokens"?: int}]. Returns {id: text|None} (None if !ok).
    Failed calls (transient 429s/timeouts) are retried up to `retries` times at HALF concurrency
    with a short pause — the burst that caused them has drained by then."""
    concurrency = FAN_CONCURRENCY if concurrency is None else concurrency
    retries = FAN_RETRIES if retries is None else retries
    out = _fan_once(calls, model, provider, reasoning, timeout_ms, concurrency)
    for _ in range(retries):
        failed = [c for c in calls if out.get(str(c["id"])) is None]
        if not failed:
            break
        time.sleep(3)
        out.update(_fan_once(failed, model, provider, reasoning, timeout_ms, max(1, concurrency // 2)))
    return out


def fan_call(prompt, max_tokens=3000, model="gpt-5.5", provider="openai-codex", reasoning="low", timeout_ms=180000):
    """Single-prompt convenience wrapper over fan_batch."""
    return fan_batch([{"id": "0", "prompt": prompt, "maxTokens": max_tokens}],
                     model, provider, reasoning, timeout_ms)["0"]
