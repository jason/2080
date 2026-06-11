#!/usr/bin/env python3
"""
test_mine_common.py — deterministic tests for the LLM backend seam (no network, no fan).

The native/fan dispatch is the open-sourcing seam: a clone with only an API key must work,
and fan must stay a pure accelerator. Run: python3 test_mine_common.py
"""
import os
import mine_common
from mine_common import backend, fan_batch


def env(key, val):
    if val is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = val


def test_backend_explicit_env_wins_over_path():
    # intent: a user pinning LLM_2080_BACKEND=native (e.g. fan is installed but its provider is
    # down) must be honored — auto-detection overriding an explicit choice is unmanageable.
    old = os.environ.get("LLM_2080_BACKEND")
    try:
        env("LLM_2080_BACKEND", "native")
        assert backend() == "native"
        env("LLM_2080_BACKEND", "fan")
        assert backend() == "fan"
    finally:
        env("LLM_2080_BACKEND", old)


def test_backend_auto_follows_fan_presence():
    # intent: a fresh clone WITHOUT fan must silently get the native backend — requiring a
    # personal CLI to run 2080 is the exact coupling the open-source cut removed.
    old, oldwhich = os.environ.get("LLM_2080_BACKEND"), mine_common.shutil.which
    try:
        env("LLM_2080_BACKEND", None)
        mine_common.shutil.which = lambda _: None
        assert backend() == "native"
        mine_common.shutil.which = lambda _: "/usr/local/bin/fan"
        assert backend() == "fan"
    finally:
        env("LLM_2080_BACKEND", old); mine_common.shutil.which = oldwhich


def test_backend_auto_prefers_key_over_claude_and_falls_back_to_claude():
    # intent: the auto chain is fan → API key → claude → native; a subscription-only user
    # (no fan, no key, claude installed) must land on the claude backend instead of the
    # native missing-key error, and a set key must NOT be silently bypassed for claude.
    old_b, old_key = os.environ.get("LLM_2080_BACKEND"), os.environ.get("OPENAI_API_KEY")
    oldwhich = mine_common.shutil.which
    try:
        env("LLM_2080_BACKEND", None)
        mine_common.shutil.which = lambda name: "/usr/local/bin/claude" if name == "claude" else None
        env("OPENAI_API_KEY", "sk-x")
        assert backend() == "native"
        env("OPENAI_API_KEY", None)
        assert backend() == "claude"
        mine_common.shutil.which = lambda name: None
        assert backend() == "native"
    finally:
        mine_common.shutil.which = oldwhich
        env("LLM_2080_BACKEND", old_b); env("OPENAI_API_KEY", old_key)


def test_claude_backend_maps_openai_default_model_to_haiku():
    # intent: every 2080 caller hardcodes model='gpt-5.5'; sent verbatim to `claude -p` that
    # 400s every call — the claude backend must map OpenAI-style names to its cheap tier
    # while letting explicit claude names and LLM_2080_MODEL pass through.
    from mine_common import _claude_model
    assert _claude_model("gpt-5.5") == "haiku"
    assert _claude_model("sonnet") == "sonnet"
    assert _claude_model("claude-haiku-4-5") == "claude-haiku-4-5"


def test_claude_once_invokes_cli_and_contains_failures():
    # intent: the claude backend must speak the shared {id: text|None} contract — a failed
    # CLI call becomes None (so fan_batch's retry net covers it), never an exception that
    # kills the whole batch.
    old_run, oldwhich = mine_common.subprocess.run, mine_common.shutil.which
    seen = []

    class R:
        def __init__(self, code, out):
            self.returncode, self.stdout, self.stderr = code, out, ""

    def fake_run(cmd, **kw):
        seen.append(cmd)
        return R(0, "pong") if "fail" not in cmd[2] else R(1, "")

    try:
        mine_common.shutil.which = lambda _: "/usr/local/bin/claude"
        mine_common.subprocess.run = fake_run
        out = mine_common._claude_once([{"id": "1", "prompt": "ping"}, {"id": "2", "prompt": "fail"}],
                                       "gpt-5.5", 60000, 4)
        assert out == {"1": "pong", "2": None}
        assert seen[0][:2] == ["claude", "-p"] and "--model" in seen[0]
        assert seen[0][seen[0].index("--model") + 1] == "haiku"
    finally:
        mine_common.subprocess.run = old_run; mine_common.shutil.which = oldwhich


def test_native_without_key_raises_actionable_error():
    # intent: a missing API key must fail loudly with the fix in the message — a None-filled
    # result dict would surface as "all categories unknown" three tools downstream.
    old_key, old_b = os.environ.get("OPENAI_API_KEY"), os.environ.get("LLM_2080_BACKEND")
    try:
        env("OPENAI_API_KEY", None); env("LLM_2080_BACKEND", "native")
        try:
            fan_batch([{"id": "1", "prompt": "hi"}])
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "OPENAI_API_KEY" in str(e)
    finally:
        env("OPENAI_API_KEY", old_key); env("LLM_2080_BACKEND", old_b)


def test_retry_refires_only_failures_at_half_concurrency():
    # intent: the retry loop is the data-integrity net for BOTH backends — if it re-fired
    # everything (duplicate cost) or nothing (silent missing votes), batch results rot.
    old_b = os.environ.get("LLM_2080_BACKEND")
    seen = []

    def fake_native(calls, model, reasoning, timeout_ms, concurrency):
        seen.append(([c["id"] for c in calls], concurrency))
        return {c["id"]: (None if c["id"] == "2" and len(seen) == 1 else "ok") for c in calls}

    old_native = mine_common._native_once
    try:
        env("LLM_2080_BACKEND", "native")
        mine_common._native_once = fake_native
        out = fan_batch([{"id": "1", "prompt": "a"}, {"id": "2", "prompt": "b"}],
                        concurrency=8, retries=1)
        assert out == {"1": "ok", "2": "ok"}
        assert seen == [(["1", "2"], 8), (["2"], 4)]
    finally:
        mine_common._native_once = old_native; env("LLM_2080_BACKEND", old_b)


def test_configured_key_and_base_url_reach_the_request():
    # intent: BYOK is the cost-control contract — if OPENAI_API_KEY/OPENAI_BASE_URL are read
    # but a default endpoint/credential is used anyway, the user's spend routes to the wrong
    # account and the knob is a lie. Prove the configured values land in the actual HTTP request.
    import io, json as _json
    old = {k: os.environ.get(k) for k in ("LLM_2080_BACKEND", "OPENAI_API_KEY", "OPENAI_BASE_URL")}
    captured = {}

    class FakeResp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        captured["body"] = _json.loads(req.data)
        return FakeResp(_json.dumps(
            {"choices": [{"message": {"content": "pong"}}]}).encode())

    old_urlopen = mine_common.urllib.request.urlopen
    try:
        env("LLM_2080_BACKEND", "native")
        env("OPENAI_API_KEY", "sk-test-byok-key")
        env("OPENAI_BASE_URL", "https://openrouter.example/api/v1")
        mine_common.urllib.request.urlopen = fake_urlopen
        out = fan_batch([{"id": "1", "prompt": "ping"}], model="m-1")
        assert out == {"1": "pong"}
        assert captured["url"] == "https://openrouter.example/api/v1/chat/completions"
        assert captured["auth"] == "Bearer sk-test-byok-key"
        assert captured["body"]["model"] == "m-1"
    finally:
        mine_common.urllib.request.urlopen = old_urlopen
        for k, v in old.items():
            env(k, v)


def test_fan_subprocess_ceiling_scales_with_batch_size():
    # intent: a flat subprocess timeout killed a 900-call judge batch live (2026-06-11) while
    # fan was healthy — the ceiling must grow with the number of waves (calls/concurrency), or
    # the prepare-once-judge-N speedup caps out at ~2 waves of work.
    old_b, old_run = os.environ.get("LLM_2080_BACKEND"), mine_common.subprocess.run
    seen = {}

    class FakeDone:
        stdout = '{"results": []}'
        stderr = ""

    def fake_run(cmd, **kw):
        seen["timeout"] = kw.get("timeout")
        return FakeDone()

    try:
        env("LLM_2080_BACKEND", "fan")
        mine_common.subprocess.run = fake_run
        fan_batch([{"id": str(i), "prompt": "x"} for i in range(320)],
                  timeout_ms=180000, concurrency=16, retries=0)
        assert seen["timeout"] >= 180 + 60 * 20  # 320/16 = 20 waves
        fan_batch([{"id": "1", "prompt": "x"}], timeout_ms=180000, concurrency=16, retries=0)
        assert seen["timeout"] < 300 + 1  # small batch keeps a tight hang backstop
    finally:
        mine_common.subprocess.run = old_run; env("LLM_2080_BACKEND", old_b)


def test_model_env_override_reaches_backend():
    # intent: LLM_2080_MODEL is the documented one-knob BYOK model selector for every tool;
    # if a script's hardcoded default wins, the knob is a lie.
    old_b, old_m = os.environ.get("LLM_2080_BACKEND"), os.environ.get("LLM_2080_MODEL")
    got = {}

    def fake_native(calls, model, reasoning, timeout_ms, concurrency):
        got["model"] = model
        return {c["id"]: "ok" for c in calls}

    old_native = mine_common._native_once
    try:
        env("LLM_2080_BACKEND", "native"); env("LLM_2080_MODEL", "my-model")
        mine_common._native_once = fake_native
        fan_batch([{"id": "1", "prompt": "a"}], model="hardcoded-default")
        assert got["model"] == "my-model"
    finally:
        mine_common._native_once = old_native
        env("LLM_2080_BACKEND", old_b); env("LLM_2080_MODEL", old_m)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
