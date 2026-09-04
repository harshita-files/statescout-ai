# StateScout AI ΓÇö Broken Feature Flag Test App

This test application provides a ground truth baseline for testing feature-flag and premium-gating policy violations ("forbidden element present").

## Known Policy Violations

The application forces the user session role/plan to `Free Tier`. According to the standard business policy, **Free Tier users must never see or interact with Premium features, specifically the "Export Data" functionality.**

This app contains a specific violation:

1.  **Premium Action Leakage:**
    *   **Element:** `<button id="btn-export-data" class="btn btn-premium">Export Data</button>`
    *   **Issue:** Fully visible and active button that triggers an export action when clicked by a `Free Tier` user.

---

## Verifying Audit Detection

When StateScout AI's crawlers explore this page under the policy:
> *"A Free Tier user must not see the Export Data button or Advanced Analytics panel."*

1.  **DOM Extraction** will find the element `button#btn-export-data`.
2.  **AX Tree Snapshot** will map the semantic node of type `button` with name `"Export Data"`.
3.  **VLM Perception Layer** will view the screenshot and identify the visual violation.
4.  **Negation Engine** will compute the intersection $L_{\text{violation}} = S_{\text{current}} \cap C_{\text{negative}}$ and successfully report the violation.