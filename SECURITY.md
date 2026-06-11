# Security Policy

## Reporting a vulnerability

Use **GitHub private vulnerability reporting** (Security tab → "Report a vulnerability" on
github.com/jason/2080). Do not open a public issue for security reports.

You should get an acknowledgment within a week. Coordinated disclosure: give us a chance to
ship a fix before publishing details.

## Supported versions

`master` only — 2080 has no maintained release branches yet.

## Scope notes (what a report here looks like)

2080's main trust boundaries, in case you're hunting:

- **External repo text → LLM prompts** (mined READMEs, commit subjects, issues, discussions).
  Prompt-injection here is bounded to analysis integrity — there is no LLM→shell/action path,
  calls are stateless, and neighbor selection is human-approved — but a way to make injected
  repo content escape that boundary is in scope.
- **OSV / GitHub API responses** (`threat_mine.py`, issue/discussions lenses): responses are
  size-capped and flow only into deterministic matching; anything that breaks that containment
  is in scope.
- **Local execution**: the tools run `git`/`gh` against cloned neighbor repos. Anything a
  hostile neighbor repo can do to the machine running a mine is in scope.
