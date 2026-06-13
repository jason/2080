"""
mine_common.py — shared substrate for 2080's mining tools (the "mine family").

2080 mines neighbor history along multiple AXES (lenses): recurring-fix → robustness spine
(`lens_mine.py --lens robustness-surface`), feature-surface → scope spine (`lens_mine.py`), and future dimensions
(integration-surface, threat-surface, operability-surface, …). Every lens shares the same shape:
read a source, abstract through an LLM, aggregate across neighbors. This module is the shared
LLM-call + JSON-extraction substrate so each new lens is a config, not new plumbing.

Three interchangeable LLM backends behind ONE seam (`fan_batch`):
  native — any OpenAI-compatible chat-completions endpoint, stdlib-only, parallel via threads.
           Bring your own key: OPENAI_API_KEY, or OPENAI_API_KEY_CMD — an external command
           (OS keychain, vault, password manager) whose stdout is the key, so it never sits
           in plaintext env/dotfiles (+ OPENAI_BASE_URL for OpenRouter/Azure/local).
  fan    — the `fan` parallel-LLM CLI, used automatically when found on PATH (a local
           accelerator with its own provider auth). Not required by anything.
  claude — Claude Code headless (`claude -p`), billed to a Claude SUBSCRIPTION via the CLI's
           OAuth login (or CLAUDE_CODE_OAUTH_TOKEN on servers). No API key needed. Default
           model haiku (cheap batch work); override with LLM_2080_MODEL=sonnet|opus|….
Auto-detection order: fan on PATH → OPENAI_API_KEY set → claude on PATH → native (which then
fails loudly with setup guidance). Pin explicitly with LLM_2080_BACKEND=native|fan|claude.
Override the model every tool uses with LLM_2080_MODEL (LLM_2080_PROVIDER is fan-only).
"""
from __future__ import annotations
import json, os, re, shlex, shutil, subprocess, sys, time
import urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

EXIT_OK, EXIT_ERR, EXIT_NOT_FOUND, EXIT_EMPTY = 0, 1, 2, 3


def write_atomic(path, text):
    """Crash-safe artifact write (tmp + os.replace): the pipeline is long and resumable, and a
    Ctrl-C/OOM mid-write must never leave a truncated JSON that a later run loads as authoritative.
    The tmp name carries the pid so two concurrent runs writing the same artifact can't
    interleave on a shared tmp file (os.replace keeps the final file whole either way)."""
    path = Path(path)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def git_text(repo, *args, timeout=60):
    """stdout of `git -C <repo> <args>`, '' on timeout — the shared read-only git helper.
    A wedged git (lazy-blob fetch, credential prompt) degrades to 'no material' instead of
    hanging a long pipeline run."""
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                              timeout=timeout).stdout
    except subprocess.TimeoutExpired:
        return ""

# Neither backend retries internally: a transient 429 becomes a None result, which downstream
# means a silently missing judge vote / assessment. Concurrency and retries are therefore coupled
# knobs: raising concurrency without retries trades wall-time for data corruption.
# Probed 2026-06-10 (default provider): 100% ok at 8/12/16/24-wide trivial bursts AND 32 realistic
# long-generation calls at 16-wide (25.5s wall vs ~100s at 4-wide). Default 16 + 1 retry as the
# safety net; re-probe if the provider or account tier changes.
FAN_CONCURRENCY = int(os.environ.get("FAN_CONCURRENCY", "16"))
FAN_RETRIES = int(os.environ.get("FAN_RETRIES", "1"))


_key_cmd_cache = {}


def resolve_api_key():
    """API key for the native backend: OPENAI_API_KEY, or — so the key never sits in plaintext
    env/dotfiles — OPENAI_API_KEY_CMD, an external command whose stdout is the key (OS keychain,
    vault, password manager; e.g. `security find-generic-password -w -s openai`). The command's
    output is cached per-process, used only in the Authorization header, and never logged."""
    k = os.environ.get("OPENAI_API_KEY", "")
    if k:
        return k
    cmd = os.environ.get("OPENAI_API_KEY_CMD", "").strip()
    if not cmd:
        return ""
    if cmd not in _key_cmd_cache:
        try:
            r = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=30)
            _key_cmd_cache[cmd] = r.stdout.strip() if r.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired, ValueError):
            _key_cmd_cache[cmd] = ""
        if not _key_cmd_cache[cmd]:
            # say WHY there's no key (never the value) — a silently-empty key falls through
            # to a different backend and the misconfiguration surfaces as a billing mystery
            print("OPENAI_API_KEY_CMD produced no key (non-zero exit, timeout, or empty stdout)",
                  file=sys.stderr)
    return _key_cmd_cache[cmd]


def backend():
    """native|fan|claude. Explicit LLM_2080_BACKEND wins; otherwise: fan on PATH (accelerator) →
    API key available (native) → claude CLI on PATH (subscription compute) → native, whose
    missing-key error then carries the setup guidance."""
    b = os.environ.get("LLM_2080_BACKEND", "").strip().lower()
    if b in ("native", "fan", "claude"):
        return b
    if shutil.which("fan"):
        return "fan"
    if resolve_api_key():
        return "native"
    if shutil.which("claude"):
        return "claude"
    return "native"


def _claude_model(model):
    """2080 callers pass OpenAI-style defaults ('gpt-5.5'); on the claude backend those map to
    haiku — the cheap/fast tier suited to batch classification/judging. Claude-ish names pass
    through, and LLM_2080_MODEL (applied in fan_batch) overrides everything."""
    m = (model or "").lower()
    return model if ("claude" in m or m in ("haiku", "sonnet", "opus")) else "haiku"


def llm_runtime():
    """Which backend/model/key source the next LLM call will use — for capability maps and
    preflight checks. Never includes secret VALUES, only their source."""
    b = backend()
    info = {"backend": b,
            "model": os.environ.get("LLM_2080_MODEL") or "gpt-5.5 (tool default)"}
    if b == "native":
        info["base_url"] = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        if os.environ.get("OPENAI_API_KEY"):
            info["key_source"] = "OPENAI_API_KEY (set)"
        elif os.environ.get("OPENAI_API_KEY_CMD"):
            info["key_source"] = "OPENAI_API_KEY_CMD (external secret command" + \
                (")" if resolve_api_key() else " — returned NOTHING; calls will fail)")
        else:
            info["key_source"] = "OPENAI_API_KEY (MISSING — calls will fail)"
    elif b == "claude":
        info["model"] = os.environ.get("LLM_2080_MODEL") or "haiku (claude-backend default)"
        info["key_source"] = "Claude Code CLI OAuth (subscription; CLAUDE_CODE_OAUTH_TOKEN on servers)"
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
    # The subprocess ceiling must scale with batch size: a batch runs in ceil(n/concurrency)
    # waves, so a flat ceiling kills any batch larger than ~2 waves of slow calls (hit live
    # 2026-06-11: a 900-call judge batch died at a flat 300s while fan was working fine).
    # Per-call timeouts are enforced INSIDE fan via timeoutMs; this is only the hang backstop.
    waves = -(-len(calls) // max(1, concurrency))
    ceiling = timeout_ms / 1000 + 60 * waves
    # All three failure shapes (hang, crash, garbage stdout) become RuntimeError — the one
    # exception type assess_target and the other callers actually catch. A raw TimeoutExpired/
    # JSONDecodeError here used to abort entire pipeline runs instead of degrading.
    try:
        r = subprocess.run(["fan"], input=json.dumps(cfg), capture_output=True, text=True,
                           timeout=ceiling)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"fan timed out after {ceiling:.0f}s ({len(calls)} calls)")
    if not r.stdout:
        raise RuntimeError(f"fan failed: {(r.stderr or '')[:300]}")
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"fan returned non-JSON output: {e}")
    out = {}
    for res in data.get("results", []):
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
    api_key = resolve_api_key()
    if not api_key:
        raise RuntimeError("native LLM backend needs OPENAI_API_KEY or OPENAI_API_KEY_CMD "
                           "(or install `fan` on PATH / set LLM_2080_BACKEND=fan)")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        texts = ex.map(lambda c: _native_one(c, model, reasoning, timeout_ms, api_key, base_url), calls)
    return {str(c["id"]): t for c, t in zip(calls, texts)}


def _claude_one(call, model, timeout_ms):
    """One headless Claude Code call (`claude -p`) — billed to the CLI's subscription OAuth.
    Returns text or None on any failure, same contract as the other backends."""
    try:
        r = subprocess.run(
            ["claude", "-p", call["prompt"], "--model", model, "--output-format", "text"],
            capture_output=True, text=True, timeout=timeout_ms / 1000)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except Exception:
        return None


def _claude_once(calls, model, timeout_ms, concurrency):
    if not shutil.which("claude"):
        raise RuntimeError("claude backend needs the Claude Code CLI on PATH "
                           "(or set OPENAI_API_KEY for native / install fan)")
    model = _claude_model(model)
    # each call is a full CLI process (~1-2s startup) — cap width below the API backends'
    with ThreadPoolExecutor(max_workers=max(1, min(concurrency, 8))) as ex:
        texts = ex.map(lambda c: _claude_one(c, model, timeout_ms), calls)
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
    b = backend()
    if b == "fan":
        once = lambda cs, conc: _fan_once(cs, model, provider, reasoning, timeout_ms, conc)
    elif b == "claude":
        once = lambda cs, conc: _claude_once(cs, model, timeout_ms, conc)
    else:
        once = lambda cs, conc: _native_once(cs, model, reasoning, timeout_ms, conc)
    out = once(calls, concurrency)
    for _ in range(retries):
        failed = [c for c in calls if out.get(str(c["id"])) is None]
        if not failed:
            break
        time.sleep(3)
        try:
            out.update(once(failed, max(1, concurrency // 2)))
        except RuntimeError:
            break  # retry pass died wholesale — keep the first pass's partial results
    return out


def fan_call(prompt, max_tokens=3000, model="gpt-5.5", provider="openai-codex", reasoning="low", timeout_ms=180000):
    """Single-prompt convenience wrapper over fan_batch."""
    return fan_batch([{"id": "0", "prompt": prompt, "maxTokens": max_tokens}],
                     model, provider, reasoning, timeout_ms)["0"]
