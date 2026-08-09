# `test-apps/` — deliberately broken demo apps

Small web apps with **known, documented violations**. They are the ground truth
for the whole system: if StateScout does not find the planted violation, the
system is wrong, not the app.

Each app ships a `violations.json` next to it listing every planted defect
(state, element, role, the policy clause it breaks) so tests can assert exact
recall rather than "found something".

Rules:

- Violations are planted **on purpose** and documented. An undocumented bug in a
  test app is a bug in the test app.
- Apps must be deterministic — no network calls, no clocks, no randomness.
- Keep them tiny. They run in CI on every push.
