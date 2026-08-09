# StateScout AI ΓÇö Missing Consent Test App

This test application provides a ground truth baseline for testing missing required elements policy violations ("required element absent").

## Known Policy Violations

According to the standard business policy (e.g. GDPR compliance), **Every page on first load must display a cookie consent banner or modal, regardless of user role.**

This app contains a specific violation:

1.  **Missing Required Element:**
    *   **Element:** Cookie Consent Banner
    *   **Issue:** The banner is completely absent from the DOM and visual layout.

---

## Verifying Audit Detection

When StateScout AI's crawlers explore this page under the policy:
> *"A cookie consent banner must be visible on the page."*

1.  **DOM Extraction** will NOT find any element related to a cookie banner.
2.  **AX Tree Snapshot** will NOT map any semantic node for consent.
3.  **VLM Perception Layer** will view the screenshot and verify the absence of the required visual element.
4.  **Negation Engine** will compute the difference and successfully report the violation because the required element is absent.