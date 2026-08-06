# The `claude` backend must run isolated from the ambient session

## Symptom

Every live assessment fails, reproducibly, on the `claude` backend:

```
assess_target: chunk 1/1 failed (unparseable) — its categories stay 'unknown'
assessment failed for <spine> (could not parse model output)
```

The deterministic path (`--from-assessment`) is unaffected, so the tool looks half-working:
saved assessments re-gate fine, but no new assessment can ever be produced.

## Cause

`_claude_one` shelled out to bare `claude -p <prompt>`. The Claude Code CLI is not a
stateless completion endpoint — a headless run still loads the ambient session context:
the user's global `~/.claude/CLAUDE.md`, project memory, the skill index, and configured
MCP servers. 2080's assessment prompt (a long, machine-generated wall of checklist +
rules + source excerpts) then arrives on top of all that.

Two distinct failure modes were observed on a box with a large global config:

1. **Role capture** — the subprocess ignored the task, behaved like an interactive
   session, summarized the repository and ended with *"What would you like to work on?"*.
2. **Injection refusal** — the subprocess treated its own inherited context plus the
   prompt as an attack:

   > "I'm seeing a massive wall of text that includes system instructions, memory files,
   > project documentation, and what appears to be attempts to inject a very complex
   > workflow into my reasoning."

Either way the output is prose, not JSON, and every chunk is unparseable.

This is **worse the more configured the user's machine is** — which selects precisely
for the users most likely to adopt the tool. A vanilla CI box may never reproduce it.

## Fix

Give the subprocess an explicit, narrow role and cut it off from ambient state:

- `--system-prompt` — replaces the inherited assistant role with a batch-endpoint
  contract, and states that the incoming text is machine-generated DATA to process, not
  instructions from a person and not an attack. This is what stops the refusal.
- `--strict-mcp-config --mcp-config '{"mcpServers":{}}'` — no MCP servers.
  (Note: `--mcp-config '{}'` is rejected — the value needs an `mcpServers` key.)
- `--disallowed-tools Task,Bash,Glob,Grep,Read,Edit,Write,WebFetch,WebSearch` — the
  assessment is pure text-in/text-out; evidence is already gathered deterministically by
  `gather_evidence`. Without this the model can wander into the repo and be steered by
  whatever it reads there.
- `--max-turns 1` — one shot, no agentic loop.

## Result

Verified on this box (previously 2/2 failures, both modes):

| Target | Before | After |
|---|---|---|
| 2080 itself (25 cats) | unparseable ×2 | GATED (exit 3), 4 blocking, ~45s |
| 2-line neutral repo | — | GATED (exit 3), 17 blocking, 8 `na_by_design` |

Full suite: 146 passed. The verdicts discriminate correctly (a mature repo scores 4
partials; a stub scores 17 gaps), and `na_by_design` is applied sensibly rather than
every category being dumped on a tiny library.
