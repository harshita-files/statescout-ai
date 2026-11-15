# ADR-003: Login and per-project sessions for the local API

- **Status:** Accepted
- **Date:** 2026-11-14
- **Track:** D (`services/api/`)
- **Supersedes:** the single-user assumption recorded in `services/api/auth.py`
  (handbook Sections 1.2 and 1.5)

## Context

`services/api/auth.py` implements one static shared secret. A client sends
`X-API-Key`, the value is compared against `STATESCOUT_API_KEY`, and that is the
whole of it. Its own docstring records the decision it was built under:

> Local-first, single-user: the handbook rules out hosted / multi-tenant auth
> for v1.

That holds as an answer to "may this client call the API at all". It answers
nothing else. In particular it has no notion of *what the caller is working on*,
and the API does have that notion everywhere else: projects are first-class
(`POST /projects`, `GET /projects/{id}`), and a scan carries a `project_id`.

The gap shows as soon as the VS Code extension is used the way it is meant to
be. One developer opens two editor windows on two repositories, each driving its
own audit against the same local API. Today those two windows are
indistinguishable: same key, same undifferentiated identity, no server-side
record that two distinct pieces of work are in flight. Nothing separates their
state, and nothing lets one be ended without touching the other.

The SRS requires that the same user working on two projects keeps a session for
each.

## Decision

Add a login step and a session per project, in `services/api/sessions.py`.

1. **One login.** `POST /auth/login` exchanges the configured
   `STATESCOUT_API_KEY` for a short-lived access token. When no key is
   configured, login succeeds without one, matching the existing rule that auth
   is off by default for local development and CI.
2. **A session per project.** `POST /auth/sessions` binds a session to one
   `project_id`. One login may hold several at once. Opening a session for a
   project that already has one re-joins it rather than forking a rival, so a
   second editor window on the same project is not a second session.
3. **Independent lifecycles.** `DELETE /auth/sessions/{id}` ends one project's
   session and leaves the login's other sessions open. `POST /auth/logout` ends
   the login and every session under it.
4. **Still one identity.** There are no user records, no passwords, no identity
   provider. The single identity is named `LOCAL_USER` rather than left implicit,
   so the store is already keyed correctly if real users ever arrive.

### What we are superseding, precisely

The handbook rules out *multi-tenant* auth for v1, and this does not introduce
it. There is still exactly one user. What changes is that the API now
distinguishes concurrent *work* by that one user, which the handbook does not
speak to and which the project model already implies.

## Alternatives considered

- **Username and password with a user store.** Rejected for v1: it introduces
  real multi-tenancy, which the handbook does rule out, and needs a password
  hashing dependency.
- **An external identity provider.** Rejected: the local API has no redirect
  handling, and a local-first tool should not require a network round trip to a
  third party in order to audit a page on `localhost`.
- **Keeping one session and passing `project_id` per request.** Rejected: it
  cannot express "end this project's work, leave the other running", which is
  the requirement.

## Consequences

**Tokens are stdlib HMAC, not JWT.** `CLAUDE.md` forbids new dependencies
without asking, and PyJWT is currently present only transitively through
`redis`. Tokens are `base64url(payload).base64url(HMAC-SHA256)`, verified in
constant time with `hmac.compare_digest`. The signing secret is
`STATESCOUT_SESSION_SECRET` if set, otherwise derived from the API key by
SHA-256 so a token can never be reversed into the key, otherwise a per-process
random value.

**Revocation is immediate.** A session token must both verify cryptographically
and still be present in the store, so ending a session takes effect at once even
though its token remains intact until expiry.

**The store is in-process.** Sessions do not survive a restart and do not span
multiple uvicorn workers. That is acceptable for the local-first deployment the
handbook describes. Moving the store to Redis, which is already a dependency, is
the documented next step if the API is ever run with more than one worker, and
the store is already behind a narrow interface for that reason.

**Nothing else changed.** `contracts.py` is untouched, no cross-module interface
moved, and the existing `X-API-Key` guard on the other routes still applies
exactly as before. The `/auth` routes are deliberately not behind that guard:
`/auth/login` is itself the gate, and the rest verify their own bearer token.

**Secrets stay out of logs and responses** (NFR-11). The API key is never echoed
back, a rejected key is not repeated in the error, and listing sessions returns
no tokens.
