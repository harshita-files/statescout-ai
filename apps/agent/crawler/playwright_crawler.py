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
from contextlib import suppress
from typing import Any

from playwright.sync_api import (
    Error as PlaywrightError,
)
from playwright.sync_api import (
    Page,
)
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from apps.agent.contracts import (
    Action,
    ActionError,
    CaptureBundle,
    NavigationError,
    Role,
)
from apps.agent.crawler.actions import execute_action, launch_session
from apps.agent.crawler.capture import DEFAULT_OUTPUT_DIR, extract_page_state

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


def _action_id(role: str, name: str, selector: str) -> str:
    """Stable content-addressed id (ADR-001 decision 1)."""
    raw = f"{role.strip().lower()}|{name.strip().lower()}|{selector.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


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
        backend_id = node.get("backendDOMNodeId")
        if backend_id:
            selector = f"[data-backend-node-id='{backend_id}']"
        else:
            selector = (
                f"[aria-label='{name}'], [name='{name}'], [placeholder='{name}'], :text('{name}')"
            )
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

    def __init__(
        self,
        role: Role = "guest",
        *,
        output_dir: str = DEFAULT_OUTPUT_DIR,
        headless: bool = True,
    ) -> None:
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
            self._session_ctx = launch_session(headless=self._headless)
            self._page = self._session_ctx.__enter__()

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
        try:
            self._start_session()
            page = self._ensure_page()
            response = page.goto(url, wait_until="load", timeout=30_000)
            if response is None:
                raise NavigationError(f"goto({url!r}) returned None")
            with suppress(PlaywrightTimeoutError):
                page.wait_for_load_state("networkidle", timeout=5_000)
            state = extract_page_state(page, url, self._output_dir)
            return self._bundle(state)
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
        try:
            page = self._ensure_page()
            raw: dict[str, Any] = {
                "type": action.kind,
                "selector": action.target,
                "url": action.target if action.kind == "navigate" else None,
                "text": action.value,
            }
            result = execute_action(page, raw, self._output_dir)
            if not result.get("success"):
                raise ActionError(f"execute_action failed: {result.get('error', 'unknown')}")
            state: dict[str, Any] = result.get("resulting_state") or {}
            return self._bundle(state)
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

        seen: set[str] = set()
        unique: list[Action] = []
        for a in collected:
            if a.action_id not in seen:
                seen.add(a.action_id)
                unique.append(a)
        return tuple(unique)

    def close(self) -> None:
        """Release the browser. Safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        if self._session_ctx is not None:
            with suppress(Exception):
                self._session_ctx.__exit__(None, None, None)
            self._session_ctx = None
            self._page = None
