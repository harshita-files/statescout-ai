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