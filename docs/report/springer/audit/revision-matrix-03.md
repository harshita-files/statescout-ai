# Revision matrix 03 (response to audit-02, score 6.9, Borderline / Major Revision)

New evidence: `docs/report/data/experiments.json` keys `E10_xpath_baseline`, `E11_two_seed_variant`, `key_map` (script `docs/report/experiments/run_experiments.py`, commit 4487574 code tree, Python 3.13.13, LangGraph 1.2.10, seed 7). E1_E3, E2, E5-E9 and meta verified identical to the stored v2 values by programmatic diff. The only code change to old functions was optional parameters on the resume sweeps with defaults reproducing the old behaviour. Nothing outside docs/report/ was touched (git status unchanged).

Correction to matrix-02 (history not rewritten): its table cites "Table 2-3 / 4-5 / 6 / 7" for items that are numbered differently in the compiled paper (the arms, loop, resume, accuracy and perturbation tables are Tables 2, 4, 5, 6 and 7 as compiled in v2; the v3 numbering changed again after the fingerprint and mutant tables were folded and re-added). Use section names (RQ1b, RQ2, RQ5) and JSON keys, not table numbers.

| ID | Sev | Action | Status | Evidence |
|---|---|---|---|---|
| F-03 | High | Added A8, an independent XPath-subset baseline over roles and visible text (no data-tag), run on in-memory data-tag-stripped copies; written once, not tuned; labelled own re-implementation, not ATUSA/Crawljax. Claims stay fixture-level | Partial: extra subject apps and real Crawljax/ATUSA baseline remain Blocked | `E10_xpath_baseline`; Sect. RQ5 |
| F-11 | Med | Table 1: axe-core NEG now checkmark (marquee rule), ZAP AE checkmark (spider), AXNav REQ set to "--" (abstract names behavioural heuristics only); MATE NEG/REQ stay "?" (abstract names no checks; IEEE page not fetchable) | Partial (MATE "?" remains, stated in caption) | bib: deque2024marquee, zap2025spider |
| F-14 | Med | Wording only: "a Gemini Flash model"; identifier not named | Blocked (Track C must reconcile docstring and `_MODEL`) | system.tex |
| F-17 | Low | Discussion and Conclusion restatements cut; total 20 pages kept | Resolved for restatements; venue limit still unknown | main.pdf |
| F-18 | Low | Environment paragraph now says script/JSON are not yet committed, no archive, LangGraph deserialisation warnings; key map added | Partial: commit/tag and archive need the authors | Sect. 5.1 |
| F-19 | Med | System text: checkpoint holds frontier, order, skips and counters; claim set is in the graph store; separation explains the resume result | Resolved | system.tex |
| F-20 | Med | RQ5 reported per mutant family (Table mutants); "at scale" removed; counts called non-independent; independent baseline added; label-rename family shows A8 losing (4 FN_F, 10 FP_R over 4 variants) and A2/A6 unaffected | Resolved | E10 families |
| F-21 | Med | See F-11; "fixed rules of one polarity each" replaced; bypass accepting heading/landmark noted | Resolved except MATE "?" | related.tex |
| F-22 | Low | Claim-set-restart result stated as specific to a one-action seed; two-seed variant (7 states, 13 pairs): checkpoint results same (13/13 twice after claim, 0/13 after edge write); restart continues only through the unclaimed seed action (2 pairs when crash at claim 1, none from claim 2); 1-12 of 13 edges persisted; positions called non-statistical | Resolved | E11 |
| F-23 | Low | D stated as observed maximum depth 3, configured limit 10 | Resolved | evaluation RQ1b |
| F-24 | Low | Arm-to-RQ-to-key column in the arms table; `key_map` in JSON; matrix-02 numbering noted above | Partial: commit/tag of the artifact is an author decision | E key_map |
| F-25 | Low | Crossref-verified pages added (Stoat 245-256, WebMate 55-69, Yandrapally 186-197, nl2spec 383-396, NL2LTL 16428-16430, issue 13); VisionDroid/Trident rename stated; grounding attribution narrowed to SeeAct, WebArena/Mind2Web/OSWorld described as benchmarks; Sun et al. wording corrected (static analysis, sitemaps, forced browsing) | Resolved; Noseevich, CREPE, ARO, Mind2Web, OSWorld pages/details remain unverified | references.bib header |
| F-26 | Low | Working-note sentence removed | Resolved | system.tex |

Not done by instruction: four "college references" not added; Track C vocabulary and Gemini identifier not decided; no plagiarism-free or detector claim.
