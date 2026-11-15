# StateScout AI - Playwright Capture Module (v0)

**Owner: Track A**

This module handles the autonomous capture layer of StateScout AI, launching a headless Chromium browser instance to extract DOM structure, accessibility trees, and screenshots from a target URL.

## Installation

Ensure you have Python 3.11+ installed. Run the following commands to install dependencies:

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

To execute the capture tool, run:

```bash
python capture.py "https://example.com"
```

You can specify a custom output directory using the `--output-dir` parameter:

```bash
python capture.py "https://example.com" --output-dir "./custom_captures"
```

### Python Import

You can also import and use the capture logic directly in other modules:

```python
from apps.agent.crawler.capture import capture_page

# Captures page and saves to default workspace captures/ folder
result = capture_page("https://example.com")
print(f"Captured DOM length: {len(result['dom'])}")
```

---

## Output JSON Schema

The script prints the results directly to `stdout` and saves a corresponding JSON file and PNG screenshot to the output directory (defaults to `captures/` at the workspace root).

Below is the exact JSON schema of the output payload:

### Successful Capture Output
```json
{
  "url": "string",
  "timestamp": "string (ISO-8601 UTC)",
  "success": true,
  "title": "string",
  "dom": "string (raw HTML page content)",
  "accessibility_tree": {
    "role": "string",
    "name": "string",
    "children": [
      {
        "role": "string",
        "name": "string",
        "value": "string/number",
        "description": "string"
      }
    ]
  },
  "screenshot_path": "string (absolute file path to PNG on disk)"
}
```

### Failed Capture Output
```json
{
  "url": "string",
  "timestamp": "string (ISO-8601 UTC)",
  "success": false,
  "title": "",
  "dom": "",
  "accessibility_tree": {},
  "screenshot_path": "",
  "error": "string (exception message details)"
}
```
### Optional probabilistic capture support

`PlaywrightCrawler(..., probabilistic_states=False)` preserves existing behavior
by default. Set `probabilistic_states=True` to enable fetch/XHR request telemetry
and best-effort readiness before captures from both `open()` and `act()`.
Readiness samples DOM markup every 50 ms and requires 200 ms of unchanged DOM,
no pending fetch/XHR requests, and 200 ms without fetch/XHR starts/completions.
A shared two-second readiness budget permits capture even when the page never
settles. Existing navigation/action timeouts remain separate from this budget.

`drain() -> tuple[str, ...]` consumes request-start labels in observed order.
Duplicates are retained, so `len(labels)` counts requests, including failed ones.
Only fetch/XHR requests from this page are observed. Labels contain the uppercase
method and URL path, for example `GET /users/:id/items/:uuid`; origin, userinfo,
query, and fragment are omitted. Whole numeric and hyphenated UUID segments
(including percent-encoded forms) become `:id` and `:uuid`. Other path segments
are preserved; this is route normalization, not arbitrary secret redaction.
Headers and bodies are never read. Disabled instances always drain to `()`.
Listeners attach once when the session starts and detach on `close()`.

The orchestrator can use the concrete optional API without changing contracts:

```python
crawler = PlaywrightCrawler(probabilistic_states=True)
try:
    initial = crawler.open(url)
    initial_requests = crawler.drain()
    crawler.drain()  # Discard any intervening observed traffic before the action.
    try:
        bundle = crawler.act(action)
    finally:
        action_requests = crawler.drain()  # Also available when the action fails.
finally:
    crawler.close()
```

Windows reflect when requests start, not guaranteed causal attribution. A late
request belongs to whichever window observes its start. Draining never resets
pending-request tracking. No orchestrator imports or contract changes are needed.
