"""PlaywrightCrawler -- Track A concrete implementation of CrawlerPort.

Wraps launch_session / execute_action / extract_page_state into the four-method
protocol the orchestrator depends on.  No logic is duplicated: this file is
only the adapter layer.

ADR-001 decisions honoured
--------------------------
1. action_id: content-addressed sha256("role|name|selector")[:16].
4. open()/act() split: different error types for different failure modes.
5. One role per instance, pinned at construction.
7. screenshot_path always populated (never None) -- we always take a screenshot.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from contextlib import suppress
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

from playwright.sync_api import (
    Error as PlaywrightError,
)
from playwright.sync_api import (
    Frame,
    Page,
    Request,
)
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from apps.agent.audit_models import BlockedNote
from apps.agent.contracts import (
    Action,
    ActionError,
    CaptureBundle,
    NavigationError,
    Role,
)
from apps.agent.crawler.actions import execute_action, launch_session
from apps.agent.crawler.capture import DEFAULT_OUTPUT_DIR, extract_page_state
from apps.agent.crawler.safety import USER_AGENT, SafetyPolicy

__all__ = ["PlaywrightCrawler"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ACTIONABLE_ROLES = frozenset(
    {
        "button",
        "link",
        "menuitem",
        "tab",
        "checkbox",
        "radio",
        "combobox",
        "listbox",
        "option",
    }
)

_KIND_MAP: dict[str, str] = {
    "link": "click",
    "button": "click",
    "menuitem": "click",
    "tab": "click",
    "checkbox": "click",
    "radio": "click",
    "combobox": "select",
    "listbox": "select",
    "option": "click",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


def _action_id(role: str, name: str, selector: str) -> str:
    """Stable content-addressed id (ADR-001 decision 1)."""
    raw = f"{role.strip().lower()}|{name.strip().lower()}|{selector.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _js_escape(text: str) -> str:
    """Escape for a JS regex literal embedded in a Playwright role selector."""
    return re.sub(r"[\\^$.*+?()\[\]{}|/]", lambda m: "\\" + m.group(0), text)


def _extract_actions(node: Any, collected: list[Action]) -> None:
    """Walk one AX-tree node (recursive).  Handles both CDP flat and nested shapes."""
    if not isinstance(node, dict):
        return

    # CDP flat format: {"nodes": [...]}
    if "nodes" in node:
        for ax_node in node.get("nodes", []):
            _extract_actions(ax_node, collected)
        return

    # Nested format (FakeCrawler / recursed children)
    role_raw = node.get("role", "")
    if isinstance(role_raw, dict):
        role_raw = role_raw.get("value", "")
    role = str(role_raw).lower().strip()

    name_raw = node.get("name", "")
    if isinstance(name_raw, dict):
        name_raw = name_raw.get("value", "")
    name = str(name_raw).strip()

    if role in _ACTIONABLE_ROLES and name:
        # Role+name survives reloads (CDP node ids and injected attributes do not), which
        # replays rely on. Exact match; nth=0 tolerates duplicates (they share an action_id).
        selector = f"role={role}[name=/^{_js_escape(name)}$/] >> nth=0"
        kind = _KIND_MAP.get(role, "click")
        collected.append(
            Action(
                action_id=_action_id(role, name, selector),
                kind=kind,  # type: ignore[arg-type]
                target=selector,
                label=f'{kind} "{name}"',
            )
        )

    for child in node.get("children", []):
        _extract_actions(child, collected)


# ---------------------------------------------------------------------------
# PlaywrightCrawler
# ---------------------------------------------------------------------------


class PlaywrightCrawler:
    """Real Playwright implementation of CrawlerPort.

    One instance per run, one role per instance (ADR-001 decision 5).

    Usage::

        crawler = PlaywrightCrawler(role="guest")
        try:
            bundle = crawler.open("https://example.com")
            for action in crawler.enumerate_actions(bundle):
                bundle = crawler.act(action)
        finally:
            crawler.close()
    """

    _safety: SafetyPolicy | None = None
    _walled: frozenset[str] = frozenset()

    def __init__(
        self,
        role: Role = "guest",
        *,
        output_dir: str = DEFAULT_OUTPUT_DIR,
        headless: bool = True,
        probabilistic_states: bool = False,
        safety: SafetyPolicy | None = None,
    ) -> None:
        self._safety = safety
        self._walled: frozenset[str] = frozenset()
        # None means readiness was disabled or no outcome was reached.
        self.last_capture_ready: bool | None = None
        self._navigation_pending: tuple[int, set[int]] | None = None
        self._probabilistic_states = probabilistic_states
        self._labels: list[str] = []
        self._pending: set[int] = set()
        self._last_network_activity = 0.0
        self._listeners: dict[
            Literal["request", "requestfinished", "requestfailed"], Callable[[Request], None]
        ] = {
            "request": self._on_request,
            "requestfinished": self._on_request_done,
            "requestfailed": self._on_request_done,
        }
        self.role = role
        self._output_dir = output_dir
        self._headless = headless
        self._session_ctx: Any | None = None
        self._page: Page | None = None
        self._closed: bool = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_page(self) -> Page:
        if self._closed:
            raise NavigationError("PlaywrightCrawler has been closed.")
        if self._page is None:
            raise NavigationError("No page open -- call open(url) first.")
        return self._page

    def _start_session(self) -> None:
        if self._session_ctx is None:
            self._session_ctx = launch_session(
                headless=self._headless, user_agent=USER_AGENT if self._safety else None
            )
            self._page = self._session_ctx.__enter__()
            if self._probabilistic_states:
                for event, handler in self._listeners.items():
                    self._page.on(event, handler)
                self._page.on("framenavigated", self._on_frame_navigated)

    def _on_request(self, request: Request) -> None:
        if (
            request.resource_type == "document"
            and request.is_navigation_request()
            and self._page is not None
            and request.frame == self._page.main_frame
        ):
            self._navigation_pending = (id(request), self._pending.copy())
        if request.resource_type not in {"fetch", "xhr"}:
            return
        self._pending.add(id(request))
        self._last_network_activity = time.monotonic()
        try:
            path = urlsplit(request.url).path or "/"
        except ValueError:
            path = "/"
        segments = []
        for segment in path.split("/"):
            decoded = unquote(segment)
            if re.fullmatch(r"[0-9]+", decoded):
                segment = ":id"
            elif re.fullmatch(
                r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                decoded,
            ):
                segment = ":uuid"
            segments.append(segment)
        self._labels.append(f"{request.method.upper()} {'/'.join(segments)}")

    def _on_frame_navigated(self, frame: Frame) -> None:
        if (
            self._page is not None
            and frame == self._page.main_frame
            and self._navigation_pending is not None
        ):
            # Drop only requests predating this committed document navigation.
            self._pending.difference_update(self._navigation_pending[1])
            self._navigation_pending = None
            self._last_network_activity = time.monotonic()

    def _on_request_done(self, request: Request) -> None:
        if self._navigation_pending is not None and self._navigation_pending[0] == id(request):
            self._navigation_pending = None
        if id(request) in self._pending:
            self._pending.discard(id(request))
            self._last_network_activity = time.monotonic()

    def drain(self) -> tuple[str, ...]:
        """Consume fetch/XHR start labels, preserving order, duplicates and failures.

        Drain before an action to discard earlier traffic, and after it to collect
        the observed window. Late requests belong to the window in which they
        start. Draining does not reset pending requests or readiness tracking.
        Disabled instances return (). No headers or bodies are inspected.
        """
        labels = tuple(self._labels)
        self._labels.clear()
        return labels

    def _wait_for_capture_ready(self) -> None:
        """Best-effort 200 ms DOM/network quiet, with a shared 2 second budget.

        Polling through Playwright dispatches request events. Each DOM read has
        its own timeout capped by the remaining budget. Expiry permits capture.
        """
        self.last_capture_ready = None
        page = self._ensure_page()
        start = time.monotonic()
        deadline = start + 2.0
        stable_since = start
        previous: str | None = None
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                dom = page.locator("html").inner_html(timeout=max(1, min(100, remaining * 1000)))
            except PlaywrightTimeoutError:
                dom = None
            now = time.monotonic()
            if dom is None or dom != previous:
                previous = dom
                stable_since = now
            if (
                dom is not None
                and now - stable_since >= 0.2
                and not self._pending
                and now - max(start, self._last_network_activity) >= 0.2
            ):
                self.last_capture_ready = True
                return
            remaining = deadline - time.monotonic()
            if remaining > 0:
                page.wait_for_timeout(min(50, remaining * 1000))
        self.last_capture_ready = False

    def _bundle(self, state: dict[str, Any]) -> CaptureBundle:
        if not state.get("success"):
            raise NavigationError(f"Capture failed: {state.get('error', 'unknown')}")
        return CaptureBundle(
            url=str(state.get("url", "")),
            dom=str(state.get("dom", "")),
            ax_tree=state.get("accessibility_tree") or {},
            screenshot_path=state.get("screenshot_path") or None,
            title=str(state.get("title", "")),
        )

    # ------------------------------------------------------------------
    # CrawlerPort
    # ------------------------------------------------------------------

    def open(self, url: str) -> CaptureBundle:
        """Navigate to *url* and capture the resulting page state.

        Raises:
            NavigationError: unreachable URL, timeout, or capture failure.
        """
        self.last_capture_ready = None
        try:
            self._gate(url)
            self._start_session()
            page = self._ensure_page()
            response = page.goto(url, wait_until="load", timeout=30_000)
            if response is None:
                raise NavigationError(f"goto({url!r}) returned None")
            if self._safety is not None and response.status == 429:
                self._safety.block(url, "rate_limit")
                raise NavigationError(f"blocked (rate_limit): {url}")
            if self._probabilistic_states:
                self._wait_for_capture_ready()
            else:
                with suppress(PlaywrightTimeoutError):
                    page.wait_for_load_state("networkidle", timeout=5_000)
            state = extract_page_state(page, url, self._output_dir)
            return self._screen(self._bundle(state))
        except (NavigationError, ActionError):
            raise
        except PlaywrightTimeoutError as exc:
            raise NavigationError(str(exc)) from exc
        except PlaywrightError as exc:
            raise NavigationError(str(exc)) from exc
        except Exception as exc:
            raise NavigationError(str(exc)) from exc

    def act(self, action: Action) -> CaptureBundle:
        """Execute *action* on the current page and capture what follows.

        Raises:
            ActionError: stale element, unknown action kind, execution failure.
            NavigationError: triggered navigation that then failed.
        """
        self.last_capture_ready = None
        try:
            page = self._ensure_page()
            if action.kind == "navigate":
                self._gate(action.target)
            elif self._safety is not None:
                self._gate(page.url)
            raw: dict[str, Any] = {
                "type": action.kind,
                "selector": action.target,
                "url": action.target if action.kind == "navigate" else None,
                "text": action.value,
            }
            if self._probabilistic_states:
                result = execute_action(
                    page, raw, self._output_dir, before_capture=self._wait_for_capture_ready
                )
            else:
                result = execute_action(page, raw, self._output_dir)
            if not result.get("success"):
                raise ActionError(f"execute_action failed: {result.get('error', 'unknown')}")
            state: dict[str, Any] = result.get("resulting_state") or {}
            return self._screen(self._bundle(state))
        except (NavigationError, ActionError):
            raise
        except PlaywrightTimeoutError as exc:
            raise ActionError(str(exc)) from exc
        except PlaywrightError as exc:
            raise ActionError(str(exc)) from exc
        except Exception as exc:
            raise ActionError(str(exc)) from exc

    def enumerate_actions(self, bundle: CaptureBundle) -> tuple[Action, ...]:
        """Derive interactable actions from *bundle*'s AX tree.

        Deterministic -- same AX tree always yields the same ordered tuple.
        Deduplicates by action_id, preserving first-occurrence order.

        Returns an empty tuple when the AX tree is missing or empty.
        """
        collected: list[Action] = []
        if bundle.ax_tree:
            _extract_actions(bundle.ax_tree, collected)

        if self._safety is not None and (bundle.url in self._walled or self._off_scope(bundle.url)):
            return ()

        seen: set[str] = set()
        unique: list[Action] = []
        for a in collected:
            if a.action_id not in seen:
                seen.add(a.action_id)
                unique.append(a)
        if self._safety is not None:
            return self._safety.filter_actions(tuple(unique))
        return tuple(unique)

    # ------------------------------------------------------------------
    # Safety (no-ops when ``safety`` is None)
    # ------------------------------------------------------------------

    def blocked_notes(self) -> tuple[BlockedNote, ...]:
        """Pages not crawled (robots, captcha, login/consent wall, cap, 429)."""
        return self._safety.blocked_notes() if self._safety else ()

    def _off_scope(self, url: str) -> bool:
        s = self._safety
        return bool(
            s and s.same_origin_only and s._start_origin and _origin(url) != s._start_origin
        )

    def _gate(self, url: str) -> None:
        """Pre-navigation checks: scope, caps, robots, then per-host rate limit."""
        if self._safety is None:
            return
        reason = self._safety.check_navigation(url)
        if reason:
            raise NavigationError(f"blocked ({reason}): {url}")
        self._safety.throttle(url)

    def _screen(self, bundle: CaptureBundle) -> CaptureBundle:
        """Count the page and record walls; walled pages are returned but not expanded."""
        if self._safety is None:
            return bundle
        self._safety.record_page(bundle.url)
        if self._safety.check_bundle(bundle):
            self._walled = self._walled | {bundle.url}
        return bundle

    def close(self) -> None:
        """Release the browser. Safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        if self._page is not None and self._probabilistic_states:
            for event, handler in self._listeners.items():
                with suppress(Exception):
                    self._page.remove_listener(event, handler)
            with suppress(Exception):
                self._page.remove_listener("framenavigated", self._on_frame_navigated)
            self._navigation_pending = None
            self._pending.clear()
        if self._session_ctx is not None:
            with suppress(Exception):
                self._session_ctx.__exit__(None, None, None)
            self._session_ctx = None
            self._page = None
