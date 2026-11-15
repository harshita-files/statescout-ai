# Revision matrix 02 (response to audit-01, score 5.7, Major Revision)

Evidence source for all new numbers: `docs/report/data/experiments.json`, produced by `docs/report/experiments/run_experiments.py` (commit 4487574, Python 3.13.13, LangGraph 1.2.10, seed 7). E1-E4 (keys `E1_E3`, `E2`) were verified identical to the earlier stored values.

| ID | Sev | Action taken | Status | Evidence / where |
|---|---|---|---|---|
| F-01 | Critical | Added arm A2: fake's oracle maps through real `negation.audit.audit`; old arm relabelled "fake algebra" (A1); arms table lists what each exercises; RQ1a and abstract reworded as a consistency check | Resolved | key `E6_real_audit_on_oracle_maps` (both arms 1.00, agree); Table 2-3, Sect. 4.2 |
| F-02 | Critical | New E5: loop counters, reference-loop parity, 25 link-order shuffles, injected submit/fill, crash/resume sweeps (in-memory checkpointer, fakes) | Resolved at fake level; live Neo4j/Redis/browser run Blocked | key `E5_loop`; Tables 4-5. Finding: checkpoint resume re-attempts the in-flight pair (11/11); claim-set-only restart never continues |
| F-03 | Critical | 64 in-memory mutants, own DOM-invariant baseline (labelled own re-implementation), claims cut to fixture level | Partially resolved; extra subject apps and real Crawljax/ATUSA baseline Blocked (not authorised) | key `E9_mutants_and_baseline`; Sect. 4.6, threats |
| F-04 | Critical | Removed "never decides existence" / "cannot be hallucinated"; stated VLM adds tags/capabilities, which subject kinds are VLM-dependent; design marked unevaluated in intro, system, discussion | Resolved | intro contribution 2, Sect. 3 end, Sect. 4.3 |
| F-05 | High | RQ2 recast as vocabulary-mismatch case study; numeric P/R removed from abstract; A4 labelled exploratory/post hoc; rename-vs-read-annotations stated as open decision | Resolved (the vocabulary decision itself remains open, per orchestrator) | Sect. 5.3 (RQ2), abstract |
| F-06 | High | V-04 hit stated as coincidental; "Genuine TP" column (A3 = 1 of 4, genuine recall 0.25; A4 = 2) | Resolved | Table 6, RQ2 text; derived from E1 missed/false_positives lists |
| F-07 | High | Proposition 1 renamed "bounded frontier executions, uninterrupted runs"; replay bound nkD added and measured (21 vs 33); SAFE column dropped from Table 1 | Resolved | model.tex; `E5_loop.uninterrupted` |
| F-08 | High | Prop. 2 demoted to an observation; falsifiable prediction tested with under/over-reporting perturbed perceivers (0 violations in 802 runs); abstract says "imply" | Resolved | key `E7_perturbed_perceivers`; Table 7 |
| F-09 | Med | "Back-edge" renamed "revisit edge", defined as non-tree edge, DFS notion disclaimed; graph stays cyclic, never pruned | Resolved | model.tex definition |
| F-10 | Med | 12 targeted fingerprint edits incl. over-merge tests; old Table 3 removed; Sect. 3.1 softened | Resolved | key `E8_fingerprint_edits` (8 detected; whitespace, 10-digit number, `req_` word, id-like value not) |
| F-11 | Med | Table 1 rebuilt: columns CYC/SAFE/GT dropped (could not verify for others); cells re-read from abstracts, ATUSA from full text; unreadable cells "?"; selection described; draft-status wording removed; StateScout marks defined as fixture-level | Partially resolved: MATE (NEG, REQ), AXNav REQ, axe-core NEG, ZAP AE remain "?" (unverified) | related.tex Table 1 |
| F-12 | Med | Added axe-core `bypass` rule (WCAG 2.4.1) and ZAP passive debug-error rule / users, with fetched sources; "no row combines" narrowed to the table | Resolved (no systematic search; no academic web-a11y crawler paper found) | 5 new bib entries |
| F-13 | Med | Working notes removed; WebTestPilot now PACMSE 3(FSE) 1933-1956 (Crossref); BACScan pages; VisionDroid cited as arXiv v2 with its real title/9 authors; pages added for Kea, Humanoid, GPTDroid, AutoDroid, AXNav, UIGuard, DroidAgent | Resolved for the 16 re-checked entries; remaining ~29 entries not re-verified (disclosed in bib header and MEMORY) | references.bib |
| F-14 | Med | Neutral "a Gemini Flash model"; mismatch of docstring (2.5) and `_MODEL` constant noted in text without a version | Blocked: Track C must resolve the docstring/constant conflict | system.tex |
| F-15 | Low | Clauses renumbered F1/V-01..R1/V-04; Fig. 1 caption fixed | Resolved | related.tex, system.tex |
| F-16 | Low | Internal org wording and unevaluated FastAPI/extension mentions removed | Resolved | system.tex |
| F-17 | Low | Limitations stated once (threats section); later sections refer back; page count 20 (16 body + 4 refs) | Partially resolved: body is 2 pages longer than v1 because of new evidence; venue limit unknown | main.pdf |
| F-18 | Low | Versions and commit recorded; seed statement corrected; archive stated as not existing | Partially resolved: no Zenodo/DOI archive (needs author decision) | Sect. 4.1 |

Also corrected: V-03 is three actions from the seed (index, login, dashboard, admin), not "two clicks".

Not done by design: no plagiarism-free claim; no detector results; the four pending "college references" were not added.
