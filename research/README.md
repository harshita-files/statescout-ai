# `research/` — isolated and cuttable (Track C)

Everything here is a research bet, deliberately kept out of the product's
dependency graph so it can be dropped without touching a line of `apps/`.

- [`finetune/`](./finetune) — InternVL LoRA / QLoRA experiments
- [`benchmark/`](./benchmark) — the negation test set and a scoped OSWorld evaluation

Nothing under `apps/` or `services/` may import from `research/`. CI enforces the
path split; the dependency direction is one-way by design.
