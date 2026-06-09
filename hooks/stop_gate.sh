#!/usr/bin/env bash
# stop_gate.sh — Claude Code Stop hook: the agent cannot claim "done" while the 2080 gate is closed.
#
# Reads <repo-root>/.2080.json (see .2080.json.example):
#   {"spine": path, "threshold": int, "fail_on": "gap"|"partial",
#    "mode": "assessment"|"live", "assessment": path}
# mode=assessment (default, recommended for hooks): gates via `check.py --from-assessment` —
#   deterministic, no LLM, sub-second. mode=live runs the full LLM assessment (~cents, ~1-2 min).
#
# Gate closed (check.py exit 3) → this hook exits 2 and prints the blocking-gap report to stderr;
# Claude Code feeds that stderr back to the agent as the reason it cannot stop. Gate open → exit 0.
# FAIL OPEN on every other condition (no config, missing spine/assessment, python error): a
# completeness gate must never wedge the user's session.
#
# Install: docs/INTEGRATIONS.md (Stop hook snippet for .claude/settings.json).

STDIN_JSON=$(cat 2>/dev/null || true)
SCRIPT_DIR=$(cd "$(dirname "$0")" 2>/dev/null && pwd) || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

exec python3 - "$SCRIPT_DIR" "$STDIN_JSON" <<'PY'
import json, os, subprocess, sys

def open_gate():  # every non-gated path ends here: the hook must never block a stop by accident
    sys.exit(0)

try:
    script_dir, stdin_json = sys.argv[1], sys.argv[2]

    # Loop guard: Claude Code sets stop_hook_active=true when a prior Stop-hook block is already
    # being handled. Honor it or a stubbornly-gated session could never end.
    try:
        if json.loads(stdin_json or "{}").get("stop_hook_active"):
            open_gate()
    except Exception:
        pass

    root = os.environ.get("CLAUDE_PROJECT_DIR")
    if not root:
        try:
            root = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                                  capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            root = ""
    root = root or os.getcwd()

    cfg_path = os.path.join(root, ".2080.json")
    if not os.path.isfile(cfg_path):
        open_gate()
    cfg = json.load(open(cfg_path))

    def resolve(p):
        return p if os.path.isabs(p) else os.path.join(root, p)

    spine = cfg.get("spine")
    if not spine or not os.path.isfile(resolve(spine)):
        open_gate()
    check = os.path.join(script_dir, "..", "check.py")
    if not os.path.isfile(check):
        open_gate()

    cmd = [sys.executable, check, root, "--spine", resolve(spine),
           "--threshold", str(cfg.get("threshold", 0)),
           "--fail-on", cfg.get("fail_on", "partial")]
    if cfg.get("mode", "assessment") != "live":
        asmt = resolve(cfg.get("assessment", ".2080-assessment.json"))
        if not os.path.isfile(asmt):
            open_gate()
        cmd += ["--from-assessment", asmt]

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode == 3:  # GATED — block the stop, feed the gap report back to the agent
        sys.stderr.write("2080 gate CLOSED: applicable required second-85% gaps remain. "
                         "Close them (or raise threshold in .2080.json) before claiming done.\n\n")
        sys.stderr.write(r.stdout or r.stderr or "")
        sys.stderr.write("\nIf gaps were just closed, refresh the saved assessment:\n"
                         "  check.py <target> --spine <spine> --save-assessment <assessment-file>\n")
        sys.exit(2)
    open_gate()  # pass AND every unexpected check.py exit code fail OPEN
except SystemExit:
    raise
except Exception:
    sys.exit(0)  # FAIL OPEN, silently
PY
