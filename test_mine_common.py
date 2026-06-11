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
