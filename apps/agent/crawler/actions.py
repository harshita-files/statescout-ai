import time
from typing import Iterator, Any
from contextlib import contextmanager
from playwright.sync_api import (
    Page,
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)

from apps.agent.crawler.capture import extract_page_state, DEFAULT_OUTPUT_DIR


@contextmanager
def launch_session(headless: bool = True) -> Iterator[Page]:
    """Context manager that yields a Playwright Page object."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        try:
            yield page
        finally:
            browser.close()


def _perform_action(page: Page, action: dict[str, Any]) -> None:
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
        try:
            page.wait_for_load_state("networkidle", timeout=short_timeout)
        except PlaywrightTimeoutError:
            pass

    elif action_type == "click":
        selector = action.get("selector")
        if not selector:
            raise ValueError("Click action missing 'selector'")
        page.click(selector, timeout=short_timeout)
        try:
            page.wait_for_load_state("networkidle", timeout=short_timeout)
        except PlaywrightTimeoutError:
            pass

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
    page: Page, action: dict[str, Any], output_dir: str = DEFAULT_OUTPUT_DIR
) -> dict[str, Any]:
    """Executes a single action on the page and returns the resulting state."""
    max_retries = 2

    result = {"success": False, "action": action, "resulting_state": None, "error": None}

    for attempt in range(max_retries + 1):
        try:
            _perform_action(page, action)
            # If we get here, the action succeeded.
            # Extract state and return.
            current_url = page.url
            state = extract_page_state(page, current_url, output_dir)
            result["success"] = True
            result["resulting_state"] = state
            return result

        except PlaywrightTimeoutError as e:
            # Transient error, we can retry
            last_error = str(e)
            if attempt < max_retries:
                time.sleep(1)  # Short delay before retry
                continue
            else:
                result["error"] = f"Timeout error after {max_retries} retries: {last_error}"
                break

        except PlaywrightError as e:
            # PlaywrightError (e.g. strict mode violation, bad selector, invalid URL) is usually permanent.
            # We do not retry.
            result["error"] = f"Playwright error: {str(e)}"
            break

        except Exception as e:
            # Other errors (e.g. ValueError from our code)
            result["error"] = f"Execution error: {str(e)}"
            break

    return result
