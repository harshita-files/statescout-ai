# `research/benchmark` — evaluation harness

Two evaluations:

1. **Negation test set** — paired UI states and policies where the correct answer
   is "this must not exist". The CVPR 2025 negation result is the thing we are
   trying not to lose to.
2. **Scoped OSWorld eval** — a narrow slice of OSWorld, used only to sanity-check
   that the agent's action selection is not degenerate.
