# Review of gap_enum.md — missing invisible-20% (Claude, reviewing Codex)

Codex's list is a good first pass on the *client-side happy-path-adjacent* gaps.
But it stops at the browser. The items most likely to eat weeks live deeper —
server-side identity, federation, and operability. These are exactly the ones a
demo never surfaces:

## Missing — server-side identity & tokens
- [ ] Server-side session/token **revocation**, not just client clear (clearing
      cookies ≠ invalidating the session; a stolen token still works).
- [ ] **Refresh-token** rotation/revocation — race between logout and an
      in-flight token refresh.
- [ ] Logout endpoint is **idempotent** (double-click / retry safe) and
      rate-limited.

## Missing — federation / SSO (the big one)
- [ ] **Single Logout (SLO)** to the IdP — does logging out of the app log out
      of the SSO provider, or leave a live IdP session that silently re-auths?
- [ ] OAuth/OIDC end-session endpoint + post-logout redirect URI registration.
- [ ] "Log out **everywhere** / all devices" vs. this-device-only — product
      decision *and* backend fan-out.

## Missing — teardown beyond cookies/localStorage
- [ ] **WebSocket / SSE / long-poll** connections closed on logout.
- [ ] **Service worker** caches and **IndexedDB** cleared (Codex named
      localStorage but not these).
- [ ] Cross-tab logout **mechanism** (BroadcastChannel / storage event) — Codex
      listed the *symptom* (multi-tab) but not the wiring.
- [ ] Push-notification subscription revoked.

## Missing — operability (you can't fix what you can't see)
- [ ] **Metrics + alerting** on logout failure rate (Codex emits an audit event
      but nothing watches it).
- [ ] Forced/remote logout: server invalidates a session → how does a live
      client *learn* and react?
- [ ] Fully **offline** logout behavior (not just degraded network).

## Verdict
Codex covered ~21 client items; this review adds ~13 that are disproportionately
the hard, weeks-long ones (identity, SSO, teardown, operability). That spread —
a competent first pass that still misses the deep half — **is the 2080 thesis in
miniature**: the gap list itself has an invisible 20%. The open question 2080
must answer: can this second-pass enumeration be made systematic, not dependent
on a sharp reviewer noticing SSO is absent?
