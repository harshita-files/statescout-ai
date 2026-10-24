# Revision matrix 05 (response to audit-04, score 7.8, Borderline)

New evidence: `E14_generated_apps` in `docs/report/data/experiments.json`; invariants in `docs/report/experiments/e14_invariants.py` (sha256 4537f85c...6d92, UTC 2026-10-09T05:18:45Z in `e14_invariants.sha256`). Diff vs stored v4 JSON: E1_E3, E2, E5-E9, E11, E13 identical. Intentional changes: E10 `note` and E12 key names/derivation notes (wording, "pre-registered" removed; E12 numbers unchanged; new `truth_variant_with_named_analytics_panel`, `A8_row_discriminating`), key_map gained E14, and `meta.code_tree_clean_vs_head` became false only because the new untracked `tests/fixtures/orchestrator/paper-subjects/` (created by fixture-forge, not by me) exists. Nothing under apps/, tests/, test-apps/ was modified by me.

| ID | Action | Status |
|---|---|---|
| F-33 | "pre-registered" removed from paper, script and JSON keys; replaced by "derived first; ordering is an authorial statement the artifact cannot evidence" | Resolved |
| F-34 | E12 A8 stated in-sample; truth variant with analytics panel stored and reported (A8 1/2, A3 0/2); consent row marked non-discriminating; abstract says "in-sample ... on these pages" | Resolved |
| F-35 | LangGraph entry notes the redirect and the 2025-12-13 archived copy and interrupts page | Resolved |
| F-36 | Script comment, E10 JSON note, MEMORY.md aligned | Resolved |
| F-37 | Duplicate node list removed | Resolved |
| F-25-residual-b | "seldom" sentence replaced by "workflow tests mostly exercise what should happen" (uncited but non-quantitative) | Resolved |
| New (E14) | Four generated apps, protocol as instructed. A3: forbidden 0/8, required 4/4 only by coincidence with 19 clean-page FP (all decoy-adjacent). A8 (written from policy files only): forbidden 3/8, required 3/4 with 4 FP (all on the three double-negation clauses; A3 has 7 there). Reported as unflattering to our approach. Same-project, AI-generated, no independence | Done, fixture-level |
| College refs | #3, #4 cited in one sentence in related work; #1, #2 in an unnumbered Acknowledgments note | Done; see verification |
| Authors/email | Four authors, institute, email supplied by user | Done |
| F-03, F-14, F-18/24, F-32, F-17 | Unchanged: independence, Track C, uncommitted artifact, MATE "?", venue limit | Blocked / partial |

Page count: 22 (was 20): +4 references, +E14 text; several tables folded into text to limit growth. Venue limit unknown.
