import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from typing import Any

from playwright.sync_api import (
    Error as PlaywrightError,
)
from playwright.sync_api import (
    Page,
    sync_playwright,
)
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from apps.agent.crawler.capture import DEFAULT_OUTPUT_DIR, extract_page_state


@contextmanager
def launch_session(headless: bool = True, user_agent: str | None = None) -> Iterator[Page]:
    """Context manager that yields a Playwright Page object."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx_args: dict[str, Any] = {"viewport": {"width": 1280, "height": 800}}
        if user_agent:
            ctx_args["user_agent"] = user_agent
        context = browser.new_context(**ctx_args)
        page = context.new_page()
        try:
            yield page
        finally:
            browser.close()


def _perform_action(page: Page, action: dict[str, Any], *, wait_network_idle: bool = True) -> None:
    """Internal helper to actually run the Playwright commands."""
    action_type = action.get("type")

    # We use a short timeout for the built-in playwright auto-waiting
    # so we can control the retry loop in execute_action.
    short_timeout = 5000

    if action_type == "navigate":
        url = action.get("url")
        if not url:
            raise ValueError("Navigate action missing 'url'")
        response = page.goto(url, wait_until="load", timeout=30000)
        if response is None:
            raise Exception("Failed to get response from URL")
        if wait_network_idle:
            with suppress(PlaywrightTimeoutError):
                page.wait_for_load_state("networkidle", timeout=short_timeout)

    elif action_type == "click":
        selector = action.get("selector")
        if not selector:
            raise ValueError("Click action missing 'selector'")
        page.click(selector, timeout=short_timeout)
        if wait_network_idle:
            with suppress(PlaywrightTimeoutError):
                page.wait_for_load_state("networkidle", timeout=short_timeout)

    elif action_type == "type":
        selector = action.get("selector")
        text = action.get("text")
        if not selector or text is None:
            raise ValueError("Type action missing 'selector' or 'text'")
        page.fill(selector, text, timeout=short_timeout)

    elif action_type == "scroll":
        direction = action.get("direction", "down")
        amount = action.get("amount", 500)
        if direction == "down":
            page.mouse.wheel(0, amount)
        elif direction == "up":
            page.mouse.wheel(0, -amount)
        else:
            raise ValueError("Scroll direction must be 'down' or 'up'")
        # Brief pause to let rendering catch up
        page.wait_for_timeout(500)
    else:
        raise ValueError(f"Unknown action type: {action_type}")


def execute_action(
    page: Page,
    action: dict[str, Any],
    output_dir: str = DEFAULT_OUTPUT_DIR,
    *,
    before_capture: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Executes a single action on the page and returns the resulting state."""
    max_retries = 2

    result = {"success": False, "action": action, "resulting_state": None, "error": None}

    action_completed = False
    for attempt in range(max_retries + 1):
        try:
            if before_capture is None:
                _perform_action(page, action)
            else:
                _perform_action(page, action, wait_network_idle=False)
            action_completed = True
            # If we get here, the action succeeded.
            # Extract state and return.
            if before_capture is not None:
                before_capture()
            current_url = page.url
            state = extract_page_state(page, current_url, output_dir)
            result["success"] = True
            result["resulting_state"] = state
            return result

        except PlaywrightTimeoutError as e:
            if before_capture is not None and action_completed:
                # Observation failure must never replay a completed opt-in action.
                result["error"] = f"Post-action timeout: {e!s}"
                break
            # Transient error, we can retry
            last_error = str(e)
            if attempt < max_retries:
                time.sleep(1)  # Short delay before retry
                continue
            else:
                result["error"] = f"Timeout error after {max_retries} retries: {last_error}"
                break

        except PlaywrightError as e:
            # PlaywrightError (e.g. strict mode violation, bad selector, invalid URL)
            # is usually permanent.
            # We do not retry.
            result["error"] = f"Playwright error: {e!s}"
            break

        except Exception as e:
            # Other errors (e.g. ValueError from our code)
            result["error"] = f"Execution error: {e!s}"
            break

    return result
