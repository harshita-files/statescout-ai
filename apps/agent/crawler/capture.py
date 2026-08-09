import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from typing import Any
from playwright.sync_api import Page, sync_playwright


def get_unique_filename(url: str) -> str:
    """Generates a unique timestamped filename base using a hash of the URL."""
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"capture_{timestamp}_{url_hash}"


DEFAULT_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "captures",
)


def extract_page_state(
    page: Page, url: str, output_dir: str = DEFAULT_OUTPUT_DIR
) -> dict[str, Any]:
    """Extracts the state from an already-open Playwright Page object."""
    os.makedirs(output_dir, exist_ok=True)
    filename_base = get_unique_filename(url)
    screenshot_filename = f"{filename_base}.png"
    screenshot_path = os.path.abspath(os.path.join(output_dir, screenshot_filename))
    json_path = os.path.abspath(os.path.join(output_dir, f"{filename_base}.json"))

    result = {
        "url": url,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "success": True,
        "title": "",
        "dom": "",
        "accessibility_tree": {},
        "screenshot_path": "",
    }

    try:
        # Capture data
        result["title"] = page.title()
        result["dom"] = page.content()

        # Accessibility tree snapshot via CDP Session
        try:
            cdp = page.context.new_cdp_session(page)
            ax_tree = cdp.send("Accessibility.getFullAXTree")
            result["accessibility_tree"] = ax_tree if ax_tree is not None else {}
        except Exception as cdp_err:
            result["accessibility_tree"] = {"error": str(cdp_err)}

        # Capture full-page screenshot
        page.screenshot(path=screenshot_path, full_page=True)
        result["screenshot_path"] = screenshot_path.replace(os.sep, "/")

        # Save result JSON to captures folder
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    except Exception as e:
        result["error"] = str(e)
        result["success"] = False

    return result


def capture_page(url: str, output_dir: str = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    """Launches headless Chromium, navigates to the URL, captures page state,
    and saves resources. Returns a dictionary containing the results.
    """
    result = {
        "url": url,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "success": False,
        "title": "",
        "dom": "",
        "accessibility_tree": {},
        "screenshot_path": "",
    }

    try:
        with sync_playwright() as p:
            # Launch headless Chromium
            browser = p.chromium.launch(headless=True)
            # Create browser context with a fixed viewport of 1280x800
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            page = context.new_page()

            # Navigate to the target URL
            # Set timeout to 30000ms (30 seconds)
            response = page.goto(url, wait_until="load", timeout=30000)

            if response is None:
                raise Exception("Failed to get response from URL (page navigation returned None)")

            # Wait for network idle to allow dynamic JS to execute/render
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                # Network idle timeout is non-fatal; proceed with capture
                pass

            # Extract page state
            result = extract_page_state(page, url, output_dir)

            browser.close()

    except Exception as e:
        result["error"] = str(e)
        result["success"] = False

    return result


def main() -> None:
    # Reconfigure stdout to use UTF-8 encoding (prevents UnicodeEncodeError on Windows terminals)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="StateScout Playwright Capture Tool (v0)")
    parser.add_argument("url", type=str, help="Target URL to capture")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            ),
            "captures",
        ),
        help="Directory to save output files (defaults to root/captures)",
    )
    args = parser.parse_args()

    result = capture_page(args.url, args.output_dir)

    # Output structured JSON payload to stdout
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if not result["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
