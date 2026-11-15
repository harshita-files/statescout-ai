# StateScout AI — VS Code Extension Setup Guide for Developers

This guide explains how any developer on the team can install, open, use, and rebuild the **StateScout AI** VS Code extension (`apps/vscode-extension`) locally in **VS Code**, **Antigravity IDE**, or **Cursor**.

---

## 1. Quick Install (Using the Pre-Built `.vsix`)

The repository already includes the packaged extension archive at:
`apps/vscode-extension/statescout-vscode-0.2.0.vsix`

### Option A — Install via Editor UI (Recommended, works in VS Code / Antigravity / Cursor)
1. Open the **Extensions** view (`Ctrl+Shift+X` on Windows/Linux, `Cmd+Shift+X` on macOS).
2. Click the **`...`** (Views and More Actions) menu at the top-right of the Extensions sidebar.
3. Select **Install from VSIX...**
4. Choose `apps/vscode-extension/statescout-vscode-0.2.0.vsix` from the repository.
5. Press `Ctrl+Shift+P` (`Cmd+Shift+P` on macOS) and run **`Developer: Reload Window`**.

### Option B — Install via Terminal CLI
```bash
# Standard VS Code
code --install-extension apps/vscode-extension/statescout-vscode-0.2.0.vsix --force

# Antigravity IDE (Windows PowerShell)
& "$env:LOCALAPPDATA\Programs\Antigravity IDE\bin\antigravity-ide.cmd" --install-extension apps/vscode-extension/statescout-vscode-0.2.0.vsix --force
```
After installing via CLI, run **`Ctrl+Shift+P` → `Developer: Reload Window`**.

---

## 2. How to Access the Extension in the Editor

Once installed and reloaded, you can open StateScout AI in three ways:

1. **Left Activity Bar (Sidebar Icon):**
   - Look at the vertical icon bar on the far left of the editor for the **StateScout AI shield/graph icon**.
   - Click the icon to open the **StateScout AI Console** sidebar, then click **`Open Audit Console`** or **`Start New Audit`**.
2. **Bottom Status Bar:**
   - Click **`🛡️ StateScout: idle`** in the bottom-left status bar.
3. **Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`):**
   - `StateScout: Open Audit Console` (`statescout.openConsole`)
   - `StateScout: Start Scan` (`statescout.startScan`)
   - `StateScout: Stop Scan` (`statescout.stopScan`)

---

## 3. Running an Audit (e.g., on StockWatch or Any Web App)

### Step 1: Ensure Backend & Target App Are Running
If your workspace has `.venv` set up, the extension automatically attempts to start the local FastAPI backend (`:8000`) and StockWatch demo server (`:8765`) in the background when activated.

To start them manually in terminals from the repo root:
```bash
# Terminal 1 — StateScout FastAPI Backend (port 8000)
uv run uvicorn services.api.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — StockWatch Demo Target App (port 8765)
uv run python test-apps/stockwatch/server.py --port 8765 --seed 7
```
*(Or using `.venv` directly on Windows: `.venv\Scripts\python.exe -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000` and `.venv\Scripts\python.exe test-apps/stockwatch/server.py --port 8765 --seed 7`)*

### Step 2: Configure & Launch the Audit in the Extension Console
Inside the **StateScout AI Audit Console** tab in your editor:
1. **Site URL:** Enter `http://127.0.0.1:8765/` (or any target URL you want to audit).
2. **Allow private/internal IP range:** Check this box when auditing `localhost` / `127.0.0.1` or internal LAN targets.
3. **Rules:** Enter plain-English rules (one per line) or click **`Generate rules from site`**. Example rules for StockWatch:
   ```text
   Guests must never see the Admin navigation item or any admin-only controls such as 'Delete user'.
   A 'Last updated' timestamp must advance whenever the displayed live prices change.
   The page must never display 'NaN', 'undefined' or 'null' to the user; missing data must be handled gracefully.
   ```
4. **Models (Optional):** Keep `None (built-in heuristics)` for fast deterministic auditing, or select `ollama`, `gemini`, `openai`, or `anthropic`.
5. **Crawl Limits & Dynamic Probes:**
   - Check **`Probabilistic mode`** to track transition probabilities and finding confidence.
   - Check **`Submit invalid values to forms`** to probe numeric forms on localhost targets.
6. Click **`Start audit`**.

### Step 3: View Live Results
As the crawl runs, the console updates in real time:
- **Progress:** Live state, transition, and violation counters + streaming execution log.
- **Exploration Graph:** Interactive force-directed SVG graph where edge thickness reflects transition probability and red nodes highlight states with violations.
- **Violations Table:** Ranked findings with severity, confidence (`stable`, `flaky`, `insufficient_evidence`), expandable page lists, DOM/AX evidence, inline screenshots, and **HTML / JSON / Markdown** export buttons.

---

## 4. Rebuilding the Extension After Code Changes

If you modify `apps/vscode-extension/src/extension.ts` or `packages/shared-types/index.ts`, rebuild the bundle (`dist/extension.cjs` + `dist/extension.js`) and repackage the `.vsix` using the zero-dependency build script (requires Node.js 22.6+):

```bash
node apps/vscode-extension/scripts/package-vsix.mjs
```

Then reinstall `apps/vscode-extension/statescout-vscode-0.2.0.vsix` and run **`Developer: Reload Window`**.
