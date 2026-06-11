"""
mine_common.py — shared substrate for 2080's mining tools (the "mine family").

2080 mines neighbor history along multiple AXES (lenses): recurring-fix → robustness spine
(`lens_mine.py --lens robustness-surface`), feature-surface → scope spine (`lens_mine.py`), and future dimensions
(integration-surface, threat-surface, operability-surface, …). Every lens shares the same shape:
read a source, abstract through an LLM, aggregate across neighbors. This module is the shared
LLM-call + JSON-extraction substrate so each new lens is a config, not new plumbing.

Two interchangeable LLM backends behind ONE seam (`fan_batch`):
  native (default) — any OpenAI-compatible chat-completions endpoint, stdlib-only, parallel via
                     threads. Bring your own key: OPENAI_API_KEY (+ OPENAI_BASE_URL for
                     OpenRouter/Azure/local servers).
  fan              — the `fan` parallel-LLM CLI, used automatically when found on PATH (a local
                     accelerator with its own provider auth). Not required by anything.
Select explicitly with LLM_2080_BACKEND=native|fan. Override the model/provider every tool uses
with LLM_2080_MODEL / LLM_2080_PROVIDER (provider is a fan concept; native ignores it).
"""
from __future__ import annotations
import json, os, re, shutil, subprocess, time
import urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

EXIT_OK, EXIT_ERR, EXIT_NOT_FOUND, EXIT_EMPTY = 0, 1, 2, 3

# Neither backend retries internally: a transient 429 becomes a None result, which downstream
# means a silently missing judge vote / assessment. Concurrency and retries are therefore coupled
# knobs: raising concurrency without retries trades wall-time for data corruption.
# Probed 2026-06-10 (default provider): 100% ok at 8/12/16/24-wide trivial bursts AND 32 realistic
# long-generation calls at 16-wide (25.5s wall vs ~100s at 4-wide). Default 16 + 1 retry as the
# safety net; re-probe if the provider or account tier changes.
FAN_CONCURRENCY = int(os.environ.get("FAN_CONCURRENCY", "16"))
FAN_RETRIES = int(os.environ.get("FAN_RETRIES", "1"))


def backend():
    """native|fan. Explicit LLM_2080_BACKEND wins; otherwise fan iff it's on PATH (accelerator),
    else native (the no-dependency default any clone can run with just an API key)."""
    b = os.environ.get("LLM_2080_BACKEND", "").strip().lower()
    if b in ("native", "fan"):
        return b
    return "fan" if shutil.which("fan") else "native"


def llm_runtime():
    """Which backend/model/key source the next LLM call will use — for capability maps and
    preflight checks. Never includes secret VALUES, only their source."""
    b = backend()
    info = {"backend": b,
            "model": os.environ.get("LLM_2080_MODEL") or "gpt-5.5 (tool default)"}
    if b == "native":
        info["base_url"] = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        info["key_source"] = "OPENAI_API_KEY (set)" if os.environ.get("OPENAI_API_KEY") \
            else "OPENAI_API_KEY (MISSING — calls will fail)"
    else:
        info["provider"] = os.environ.get("LLM_2080_PROVIDER") or "openai-codex (tool default)"
        info["key_source"] = "fan CLI's own provider auth"
    return info


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


def _native_one(call, model, reasoning, timeout_ms, api_key, base_url):
    """One OpenAI-compatible chat-completions request (stdlib). Returns text or None on any
    failure — same contract as a fan !ok result, so fan_batch's retry loop covers both backends."""
    body = {"model": model, "max_completion_tokens": call.get("maxTokens", 3000),
            "messages": [{"role": "user", "content": call["prompt"]}]}
    if reasoning:
        body["reasoning_effort"] = reasoning
    for attempt in (1, 2):  # attempt 2: strip reasoning_effort — many compatible servers 400 on it
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/chat/completions", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout_ms / 1000) as r:
                msg = json.loads(r.read()).get("choices", [{}])[0].get("message", {})
                return msg.get("content") or None
        except urllib.error.HTTPError as e:
            if e.code == 400 and attempt == 1 and "reasoning_effort" in body:
                body.pop("reasoning_effort")
                continue
            return None
        except Exception:
            return None
    return None


def _native_once(calls, model, reasoning, timeout_ms, concurrency):
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("native LLM backend needs OPENAI_API_KEY "
                           "(or install `fan` on PATH / set LLM_2080_BACKEND=fan)")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        texts = ex.map(lambda c: _native_one(c, model, reasoning, timeout_ms, api_key, base_url), calls)
    return {str(c["id"]): t for c, t in zip(calls, texts)}


def fan_batch(calls, model="gpt-5.5", provider="openai-codex", reasoning="low", timeout_ms=180000,
              concurrency=None, retries=None):
    """Run N prompts concurrently through the active backend (see module docstring).
    `calls` = [{"id": str, "prompt": str, "maxTokens"?: int}]. Returns {id: text|None} (None on
    failure). Failed calls (transient 429s/timeouts) are retried up to `retries` times at HALF
    concurrency with a short pause — the burst that caused them has drained by then.
    LLM_2080_MODEL / LLM_2080_PROVIDER override model/provider for EVERY 2080 tool at once —
    the bring-your-own-key / provider-selection seam lives here, not per-script."""
    model = os.environ.get("LLM_2080_MODEL") or model
    provider = os.environ.get("LLM_2080_PROVIDER") or provider
    concurrency = FAN_CONCURRENCY if concurrency is None else concurrency
    retries = FAN_RETRIES if retries is None else retries
    once = (lambda cs, conc: _fan_once(cs, model, provider, reasoning, timeout_ms, conc)) \
        if backend() == "fan" else (lambda cs, conc: _native_once(cs, model, reasoning, timeout_ms, conc))
    out = once(calls, concurrency)
    for _ in range(retries):
        failed = [c for c in calls if out.get(str(c["id"])) is None]
        if not failed:
            break
        time.sleep(3)
        out.update(once(failed, max(1, concurrency // 2)))
    return out


def fan_call(prompt, max_tokens=3000, model="gpt-5.5", provider="openai-codex", reasoning="low", timeout_ms=180000):
    """Single-prompt convenience wrapper over fan_batch."""
    return fan_batch([{"id": "0", "prompt": prompt, "maxTokens": max_tokens}],
                     model, provider, reasoning, timeout_ms)["0"]
