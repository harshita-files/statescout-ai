# Proposal for Track A: network capture, readiness and real actions

- **Owner:** Track A (`apps/agent/crawler/`). Drafted by Track B, which does not write there.
- **Status:** Proposal. Cites `docs/adr-002-probabilistic-network-state-model.md` (ADR-002, Proposed) and does not restate or amend it. `contracts.py` is untouched.
- **Basis:** read-only inspection of the uncommitted working-tree diff in `apps/agent/crawler/` and of `apps/agent/orchestrator/dynamic.py`. Nothing here was run; no test result is claimed.

## Problem

ADR-002 needs from the crawler: sanitized `METHOD /template` telemetry per action window, a bounded and observable readiness outcome, and actions the orchestrator can actually replay and explore. `docs/handoff/PROJECT_STATE.md` section 7 lists the gaps: blind `networkidle` wait (5 s, error suppressed), no network interception, and `fill`/`select`/`submit`/`back` not implemented, plus a selector that does not exist in the real DOM.

## What the pending diff already does (read from the diff, not executed)

All of it is behind `PlaywrightCrawler(..., probabilistic_states=False)`; default behavior is intended to be unchanged.

| Need | In the diff | Evidence |
| --- | --- | --- |
| Telemetry via `NetworkObservations` | `PlaywrightCrawler.drain() -> tuple[str, ...]` matches the protocol in `orchestrator/dynamic.py:21`. Listeners on `request`, `requestfinished`, `requestfailed`, `framenavigated`; only `fetch`/`xhr`; label is `METHOD path`; query, fragment, origin, userinfo dropped; duplicates and order kept; disabled instance drains `()`. Listeners removed in `close()`. | `playwright_crawler.py` `_on_request`, `drain` |
| Template sanitizing | Whole-numeric segments become `:id`, hyphenated UUID segments become `:uuid` (after percent-decoding). | `_on_request` |
| Action-window attribution | Window = requests that START between two `drain()` calls. Doc says explicitly this is not causal attribution. Failed actions can be drained in `finally`. | README addition |
| Bounded readiness | `_wait_for_capture_ready`: samples `html` inner_html every ~50 ms, needs 200 ms unchanged DOM, no pending fetch/XHR, 200 ms without request activity; shared 2 s budget; expiry still captures. Outcome in `last_capture_ready` (`True`/`False`/`None`). | `_wait_for_capture_ready` |
| Replace blind `networkidle` | When opted in, `open()` and `act()` skip the `networkidle` wait (`wait_network_idle=False`) and call the readiness hook through `execute_action(before_capture=...)`. | `actions.py`, `act()` |
| No double-fire on post-action timeout | Opt-in: a timeout after the action completed breaks out instead of retrying. | `execute_action`, `action_completed` |
| Tests | `tests/unit/crawler/test_probabilistic.py` (untracked, ~17 test functions by name: default unchanged, windows, bounded readiness, pending not forgotten on drain, no re-fire, etc.). Whether they pass is unknown. | file listing |

## What is still missing or doubtful

1. **Real `fill`/`select`/`submit`/`back`.** `actions._perform_action` still handles only `navigate`, `click`, `type`, `scroll`. `Action.kind` values from the contract (`fill`, `select`, `submit`, `back`) are passed through as `type` and reach `raise ValueError("Unknown action type")`. Note also `fill` != `type`, so a `fill` action from `enumerate_actions` would fail even though `page.fill` is used for `type`. Unchanged by the diff.
2. **`enumerate_actions` does not return form fields**, and `_KIND_MAP` maps `combobox`/`listbox` to `select` (which cannot execute). Unchanged.
3. **Invalid selector.** `_extract_actions` still builds `[data-backend-node-id='N']` (playwright_crawler.py:115). No such attribute exists in real pages. Unchanged.
4. **Readiness outcome is not on the contract.** `last_capture_ready` is a crawler attribute read by the runner through `getattr(ports.network, "last_capture_ready", None)`. It carries no elapsed time, which signal failed, or deadline value (ADR-002 asks for these). The 2 s budget and the 50/200 ms constants are hard-coded.
5. **Readiness is DOM-string polling.** Reading `inner_html` of the whole document every 50 ms is costly on large pages and treats any DOM mutation (clocks, tickers, animations) as unstable; this will hit the 2 s deadline on exactly the dynamic pages the work targets. No app-ready-selector option exists (ADR-002 lists it). Uncertain until measured.
6. **Sanitizing is route normalization, not redaction** (the README says so). Non-numeric ids, hex tokens, emails, JWT-like segments and slugs pass through. The orchestrator regex (`[A-Za-z0-9_/{}:.-]`) will silently DROP labels containing `%`, `@`, `~`, etc., and will ACCEPT `abc123def456...` token segments. Producer-side templating must be stronger.
7. **Scope of observed traffic.** Only `fetch`/`xhr` from the single page; no `sendBeacon`, WebSocket, EventSource, form-POST navigations, or iframe/popup/worker traffic. A form submit that navigates is invisible as an endpoint call unless the document request is counted. Undecided in ADR-002.
8. **Late/background requests.** Polling that starts inside a window is attributed to it. No marker distinguishes background polling from action-caused calls.
9. **Replay safety.** `click` is in `REPLAY_SAFE_KINDS`; nothing in the crawler signals that an action is state-mutating (ADR-002 risk "Replay side effects").
10. **Where the diff sits.** It was written by another session in Track A's module (see `RECONCILIATION.md`); it has not been reviewed by Track A, and there is no branch/PR.

## Exact change requested (Track A)

1. Add real `fill`, `select`, `submit`, `back` handling in `actions._perform_action` (`page.fill`, `page.select_option`, `locator.press("Enter")`/`form.requestSubmit()`, `page.go_back`). Accept both `fill` and `type` spellings or map `fill` to the `page.fill` branch.
2. Make `enumerate_actions` emit `fill`/`select` for inputs and `<select>`, and `submit` for form submit controls, with `value` supplied by a config/fixture rather than invented (needs a Track A/B decision on test data; do not hard-code credentials, NFR-11).
3. Replace `[data-backend-node-id=...]`: either resolve through CDP `DOM.resolveNode(backendNodeId)` to an element handle held by the session, or generate a stable CSS/role-name locator (`get_by_role(role, name=...)`), consistent with the action_id hash (ADR-001 A-1). Selector stability across replay must be tested.
4. Make readiness configurable (deadline, quiet window, optional ready selector) and expose a small outcome object on the crawler: `ready | deadline | none`, elapsed ms, deadline ms. Replace whole-document `inner_html` polling with a `MutationObserver` injected via `add_init_script`/`evaluate` (counts mutations in a window) or a cheaper size/hash signal. Keep the finite deadline.
5. Strengthen the template step: also template UUID-like, long hex (>=16), long base64url, email-like and any segment over N chars or containing `=`/`@`; keep whitelisted static segments. Prefer unknown segments becoming `:seg` over leaking.
6. Document and test window boundaries: navigation commit, action start, late response after the next drain.
7. Optionally flag an action `mutating` heuristically (POST/PUT/PATCH/DELETE seen during click) so the orchestrator can learn not to replay it. Interface sketch below; requires a Track A/B decision.

## Interface sketch (no contract change)

```python
# apps/agent/crawler/playwright_crawler.py (Track A)
@dataclass(frozen=True, slots=True)
class CaptureReadiness:
    outcome: Literal["ready", "deadline", "disabled"]
    elapsed_ms: float
    deadline_ms: float
    signals: tuple[str, ...]   # e.g. ("dom_quiet", "no_pending_xhr")

class PlaywrightCrawler:
    last_capture_ready: bool | None          # kept for the existing runner
    last_readiness: CaptureReadiness | None  # new, optional
    def drain(self) -> tuple[str, ...]: ...  # NetworkObservations, unchanged
```

`NetworkObservations` stays the experimental local Protocol (ADR-002 says it is not a frozen cross-track contract). Any envelope with window IDs or availability needs a new ADR section agreed by A/B/D.

## Tests (failing first, Track A, `tests/unit/crawler/`)

- `fill`/`select`/`submit`/`back` each executed against a local fixture page; unknown kind still raises `ActionError`.
- Selector resolves on a page that has no `data-backend-node-id` attribute; same action_id across two loads.
- Readiness: delayed render, 1 s polling, never-quiet page terminates by the deadline with outcome `deadline`; app-ready selector short-circuits.
- Sanitizer table test: UUID, numeric, hex token, JWT, email, percent-encoded, long segment, query with secret, userinfo; none leak. Property test: output always matches the orchestrator whitelist or is dropped explicitly (count dropped).
- Window tests: late response, two requests to one endpoint in a click, failed action still drains.
- Default-off parity: with `probabilistic_states=False` behavior and call arguments match the pre-diff code.

## Risk

- Real-browser behavior is unverified; the existing unit tests are fakes/mocks (uncertain: only the diff was read).
- A faster or stricter readiness signal may change fingerprints and therefore state counts.
- Form submit and `fill` cause side effects against the app under test; they must stay out of `REPLAY_SAFE_KINDS` unless Track B agrees (that set is Track B's).
- Moving selectors off `data-backend-node-id` changes `action_id` values (ADR-001 A-1 hash includes the selector); any stored visited pairs from earlier runs become unmatched.

## Effort

About 5 to 7 working days: actions + enumeration 2 to 3, selector resolution 1 to 1.5, readiness rework 1 to 1.5, sanitizer + tests 1. Review and integration with B/D add about 1 day.
