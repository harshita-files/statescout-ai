---
hide:
  - navigation
  - toc
---

# Reporting API

The reporting API (`services/api`, Track D) runs scans, streams their progress, and
serves the reports. This reference is generated at build time from the API's own
OpenAPI document, so it always matches the deployed code. You can also download
the raw <a href="../../openapi.json"><code>openapi.json</code></a> and import it into
Postman or any other client.

The live event stream, `WS /scan/{scan_id}/live`, is a WebSocket and is not part of
the OpenAPI document; it is described in the
[API module documentation](../documentation/modules/api.md).

<div id="redoc"></div>
<script src="https://cdn.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js"></script>
<script>
  // GitHub dark colours, to match the rest of the site.
  Redoc.init("../../openapi.json", {
    hideHostname: true,
    theme: {
      colors: {
        primary: { main: "#3fb950" },
        success: { main: "#3fb950" },
        warning: { main: "#d29922" },
        error: { main: "#f85149" },
        text: { primary: "#e6edf3", secondary: "#8b949e" },
        border: { dark: "#30363d", light: "#21262d" },
        http: { get: "#3fb950", post: "#58a6ff", put: "#d29922", delete: "#f85149" }
      },
      schema: { nestedBackground: "#161b22", typeNameColor: "#8b949e", linesColor: "#30363d" },
      typography: {
        fontFamily: "inherit",
        headings: { fontFamily: "inherit" },
        code: { color: "#e6edf3", backgroundColor: "#161b22" },
        links: { color: "#3fb950" }
      },
      sidebar: { backgroundColor: "#0d1117", textColor: "#e6edf3", activeTextColor: "#3fb950" },
      rightPanel: { backgroundColor: "#161b22", textColor: "#e6edf3" },
      codeBlock: { backgroundColor: "#010409" }
    }
  }, document.getElementById("redoc"));
</script>
