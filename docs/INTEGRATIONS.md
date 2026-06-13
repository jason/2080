# 2080 Integrations — running the gate without an LLM

`check.py` splits the expensive part (one LLM assessment, ~cents, ~1-2 min) from the cheap part
(the deterministic gate). That split is what makes hooks and CI possible:

```sh
# 1. Assess once (live LLM), saving the raw assessment:
./check.py . --spine checklists/<spine>.json --save-assessment .2080-assessment.json

# 2. Re-gate any number of times — fast, free, deterministic, no LLM:
./check.py . --spine checklists/<spine>.json --from-assessment .2080-assessment.json
```

Exit codes: `0` pass · `1` usage/err · `2` not found · `3` GATED (required gaps remain).

## Refresh workflow (assessments go stale)

A saved assessment is a snapshot of the repo at assess-time. After meaningful changes — closing a
gap, adding a feature surface, restructuring — re-run step 1 to refresh it. The gate never
re-reads your source in `--from-assessment` mode; a stale assessment gates (or passes) on old
truth. Rule of thumb: refresh after every work session that touched a blocking category, and
commit the refreshed `.2080-assessment.json` so CI sees it.

## Claude Code Stop hook

`hooks/stop_gate.sh` blocks the agent from claiming "done" while the gate is closed. Gate closed →
hook exits 2 and the blocking-gap report goes back to the agent as the reason it cannot stop.
Everything else (no config, missing files, errors) **fails open** — the gate never wedges a session.

1. Copy `.2080.json.example` to `.2080.json` in the target repo root and point `spine` /
   `assessment` at real files. `mode: "assessment"` (default) is the right choice for hooks;
   `mode: "live"` runs the full LLM assessment on every stop (slow, costs cents).
2. Add the hook to the target repo's `.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          { "type": "command", "command": "/path/to/2080/hooks/stop_gate.sh" }
        ]
      }
    ]
  }
}
```

The hook honors `stop_hook_active` (Claude Code's loop guard), so a gated session can still be
ended by the user.

## CI (GitHub Actions)

`.github/workflows/2080-gate.yml` ships dormant: on push/PR it runs
`check.py --from-assessment .2080-assessment.json --spine <from .2080.json> --json` **iff** both
`.2080.json` and `.2080-assessment.json` are committed; otherwise it logs
"no committed assessment — gate skipped" and passes. Exit 3 fails the build.

Live LLM mode in CI is deliberately out of scope: it would need `fan` plus Codex OAuth credentials
on the runner. Keep CI on the committed-assessment path; refresh assessments locally where the
auth lives.

## Secrets and credential handling

2080 is bring-your-own-key and deliberately never persists credentials:

- **Source**: keys are read from the environment (`OPENAI_API_KEY`, optional
  `OPENAI_BASE_URL` / `LLM_2080_MODEL`), from an external secret command
  (`OPENAI_API_KEY_CMD`, below), or supplied transparently by the `fan` CLI's own
  auth when it is on PATH. No tool reads keys from config files, and `.2080.json` has no
  credential fields — committing it is always safe.
- **Storage**: nothing under 2080 writes a key to disk — not in saved assessments, caches
  (`~/.cache/2080-*`), emitted task queues, or measurement JSONs. Keys exist only in process
  environment for the lifetime of a run.
- **Diagnostics**: the BYOK preflight (`./2080 check --json`, `llm` field) reports which
  SOURCE a key came from (env var name / fan), never the value or any prefix of it.
- **Recommended local setup — `OPENAI_API_KEY_CMD`**: point 2080 at your OS keychain, vault,
  or password manager and never materialize the key in env/dotfiles at all:
  `export OPENAI_API_KEY_CMD='security find-generic-password -w -s openai'` (macOS Keychain),
  `'op read op://dev/openai/key'` (1Password), `'pass show openai'`. The command's stdout is
  used as the key (cached per-process), flows only into the Authorization header, and is
  never logged; the preflight reports the source as `OPENAI_API_KEY_CMD`, never the value.
- **CI**: the shipped workflow is deliberately LLM-free (gates on the committed assessment),
  so CI needs NO secret at all. If you do run live assessment in CI, use the platform's
  secret store (GitHub Actions `secrets.*`) — never a committed file.
