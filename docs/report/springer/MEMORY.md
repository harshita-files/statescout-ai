# MEMORY.md

Persistent working memory for the StateScout Springer-format paper. Memory is a working aid, not an authority: the repository files named below override it.

## 1. Project Overview
- Title (working): "StateScout: Auditing What a User Interface Must Not Contain, and What It Must".
- Domain: web UI testing / policy-conformance auditing; test oracles; VLM perception.
- Problem: UIs can expose what a role should not see (forbidden-present) or omit what policy requires (required-absent) even when the server enforces authorization; workflow tests do not catch this.
- System (from /CLAUDE.md): LangGraph orchestrator, Playwright crawler, VLM perception, negation engine, Neo4j graph store, Redis visited-pair cache.
- Research questions (paper): RQ1 audit logic + graph structure; RQ2 perception grounding and error direction; RQ3 necessity of required-absent; RQ4 fingerprint stability/sensitivity.
- Authors/affiliation: UNKNOWN. Placeholders in main.tex. The old drafts named "Team 46, Amrita Vishwa Vidyapeetham"; not carried over (unconfirmed for this venue).

## 2. Core Contribution
Claims (scoped as "we formalise and combine", per novelty-analysis.md):
1. Polarity-typed, role-scoped policy oracle: forbidden-present = S ∩ F, required-absent = R \ S, over a semantic state abstraction.
2. Error-direction asymmetry (Proposition 2): under-reporting perception can only miss forbidden and only falsely alarm on required; over-reporting reverses it. Motivates negation-safe division of labour (deterministic DOM/AX decides existence; VLM only annotates). The division of labour is a DESIGN claim, no empirical support yet.
3. Cyclic, claim-before-execute exploration (at-most-once per (state_id, action_id) pair; kind-restricted replay). Engineering contribution, not headline.
4. Small reproducible evaluation separating audit-logic guarantees from perception quality.
NOT claimed: first crawler/state graph; novel cyclic graph; first to detect missing elements; novel fingerprinting; novel loop prevention; broken-access-control detection (OWASP A01); NL-policy-driven audit (compiler not implemented); end-to-end 100% recall; solving VLM negation.

## 3. Methodology
- Model: LTS M_r=(Q,A,delta,q0); capture kappa=(url,DOM,AX,screenshot); fingerprint phi=SHA-256 of normalised URL|DOM|AX.
- Exploration graph is CYCLIC (never DAG; revisit/"back" edges never pruned; paper says "revisit edge", code field is_back_edge). Loop prevention = visited (state_id, action_id) claim set only; claim inserted before execute, edge persisted after.
- Proposition 1 = "bounded frontier executions, uninterrupted runs" (nk executions, nkD replay re-fires, D = observed max depth 3, configured limit 10). It is NOT an at-most-once guarantee.
- REPLAY_SAFE_KINDS = {navigate, click, back} (apps/agent/orchestrator/state.py). `click` IS replay-safe; residual risk stated.
- Audit: Eq.(1) forbidden present, Eq.(2) required absent; exact matching after whitespace/case normalisation. The error-direction result (labelled Proposition 2 in the paper, an elementary monotonicity observation), tested by perturbed perceivers (E7).
- Perception: deterministic DOM/AX correlator; a Gemini Flash model channel exists (not wired, not evaluated; paper names no version; gemini.py docstring says 2.5 Flash but _MODEL='gemini-3.6-flash'; Track C must reconcile). VLM can add tags/capabilities, so grounding errors remain.
- Checkpoint (LangGraph) holds frontier, order, skips, counters; claim set is in GraphPort (Redis). Resume re-runs `act` without consulting claims (E5), which matches LangGraph's documented node-restart behaviour.

## 4. Dataset and Experimental Setup
- Subject: test-apps/broken-admin (6 pages, role guest, 3 forbidden + 1 required clause, V-01..V-04; V-03 is 3 actions from the seed). Extra subjects (E12, read-only): broken-rbac-demo, missing-consent-demo, broken-feature-flag-demo (same project, tiny, unannotated; truth derived from READMEs before running).
- Script docs/report/experiments/run_experiments.py -> docs/report/data/experiments.json. Environment recorded in `meta`: Python 3.13.13, LangGraph 1.2.10, git HEAD 4487574 (code tree clean; script and JSON untracked). Seed 7 for RQ2 perturbations, RQ4 noise, compound mutants, shuffles; the rest is deterministic. No browser, Neo4j, Redis or network.
- Arms: A1 oracle+fake algebra, A2 oracle+production audit, A3 DOM channel, A4 lexical (post hoc), A5 perturbed oracle, A6 tag script, A7 loop, A8 XPath script (element types, link targets, text; own re-implementation, not ATUSA/Crawljax).
- key_map in JSON: RQ1a E1_E3,E6; RQ1b E5,E11; RQ2 E1_E3,E7; RQ3 E1_E3,E6; RQ4 E2,E8; RQ5 E9,E10,E12,E13.

## 5. Verified Results (all in experiments.json; E1-E11 verified identical across revisions except the E11 hash-seed field)
- E1/E3/E4: oracle 4/0/0; oracle F-only 3/0/1; DOM channel 2/5/2 (P .286 R .5; genuine TP 1, V-04 hit coincidental); lexical 2/0/2 (post hoc).
- E2: 300 naive vs 6 normalised ids. E8: 8 of 12 edits change the id; whitespace, 10-digit number, req_ word, id-like value do not.
- E5: 11 pairs, 0 duplicates, 9 replays, 21 steps (1.91/pair), 6 revisit edges, frontier_exhausted; submit/fill leaves 4 states, 3 skipped, 1/4 found; checkpoint resume re-attempts the in-flight pair 11/11 (after claim), 0/11 after edge write; fresh browser leaves graph incomplete 3/22; claim-set-only restart never continues on a one-action seed. E11 (two seed actions, 13 pairs): same checkpoint results; restart continues only via the unclaimed seed action.
- E6: real audit on oracle maps 1.00. E7: 0 violations of predicted direction in 802 runs.
- E9/E10/E13: 68 variants of one app; A2/A6/A8 exact on 64 shape-preserving; A3 exact on none; A8 loses on label renames (Admin 1 FN_F, Delete user 1 FN_F, Skip navigation 5 FP_R); A2 on stripped fixture P .17 R .25.
- E12: A8 3/3 TP 0 FP; A3 (README subjects) 1/3, vacuous consent hit; post hoc tagger vocabulary: finds rbac+flag defects, flags admin.html.

## 6. Related Work and Citation Map
- references.bib: 53 entries (49 + 4 college references), all cited, bibtex 0 warnings. Header lists which entries were re-checked (Crossref/fetch) in rev. 2-4; the rest are from the 2026-09-22 novelty search and not re-verified. Pages added from Crossref in rev. 3 (Stoat, WebMate, Yandrapally, nl2spec, NL2LTL); Noseevich pages dropped (unverified).
- Web a11y/DAST sources (fetched 2026-10-09): axe-core, axe bypass and marquee rules, WCAG 2.4.1, ZAP passive rules, users, spider; LangGraph durable execution (statements seen in search excerpts).
- VisionDroid is cited as arXiv v2 (Trident; 9 authors); v1 had 8 authors and the VisionDroid title.
- Table 1 columns AE POL NEG REQ ROLE MM (CYC/SAFE/GT dropped as unverifiable). Open cells: MATE NEG/REQ "?"; AXNav REQ "~". StateScout marks are fixture-level only.
- Negation citations (alhamoud2025negation, yuksekgonul2023aro, ma2023crepe) concern natural images; motivation only.

## 7. Required Paper Format
- svproc (unmodified svproc.cls), \mainmatter, abstract 70-150 words (now 146), plain + natbib, no amsthm, packages booktabs amssymb tikz multirow. Files: main.tex, sections/{introduction,related,model,system,evaluation,discussion,conclusion}.tex, references.bib, Makefile. Current: 20 pages (16 body + 4 refs), 0 overfull, 1 OT1 font warning, bibtex 0 warnings. Architecture figure removed in rev. 4 to hold 20 pages.

## 8. Known Limitations (current)
- One fixture plus three tiny same-project apps; no independent subject; no real Crawljax/ATUSA baseline (BLOCKED: authors). A8 written knowing labels; its "written before first run" is unevidenced.
- No browser-driven, VLM or hybrid result (BLOCKED: Track C vocabulary decision, API key). Crash test is in-memory with fakes; no live Neo4j/Redis/durable checkpointer.
- MATE NEG/REQ "?" (abstract not obtainable). ~25 bib entries not independently re-verified. LangGraph durable-execution statements were read in search excerpts, not in a direct section fetch.
- Artifact untracked and unarchived; venue/page limit unknown; authors are placeholders; plagiarism: no corpus, no claim of plagiarism-freeness; no detector results.
- Pending with the user: four "college references" (NOT added); Track C vocabulary decision; Gemini identifier.

## 9. Auditor Findings
Audit 1 (2026-10-09, score 5.7, Major Revision). Full per-finding status: audit/revision-matrix-02.md.
| ID | Sev | Status after v2 |
|---|---|---|
| F-01 | Critical | Resolved (real audit on oracle maps, E6) |
| F-02 | Critical | Resolved at fake level (E5); live-stack run blocked |
| F-03 | Critical | Partial: mutants + own baseline (E9); extra subjects and real Crawljax/ATUSA baseline BLOCKED |
| F-04 | Critical | Resolved (wording) |
| F-05 | High | Resolved (recast); vocabulary decision still open (Track C) |
| F-06 | High | Resolved (genuine TP column) |
| F-07 | High | Resolved |
| F-08 | High | Resolved (E7 perturbation test) |
| F-09 | Med | Resolved (revisit edge) |
| F-10 | Med | Resolved (E8) |
| F-11 | Med | Partial: 4 cells still "?" |
| F-12 | Med | Resolved (axe-core, ZAP) |
| F-13 | Med | Resolved for 16 re-checked entries; ~29 not re-verified |
| F-14 | Med | Blocked: gemini.py docstring says 2.5 Flash, `_MODEL = "gemini-3.6-flash"`; paper names no version |
| F-15..F-16 | Low | Resolved |
| F-17 | Low | Partial (20 pages: 16 body + 4 refs) |
| F-18 | Low | Partial (no archive DOI) |

## 10. Revision History
| Version | Date | Changes | Findings resolved / remaining | Score |
|---|---|---|---|---|
| v1 (Springer) | 2026-10-09 | New svproc rewrite from docs/report/paper/ and ieee/; dropped non-reproducible counters; arm-composition disclosure; 19 pages | n/a | 5.7 (audit 1) |
| v2 | 2026-10-09 | Added experiments E5-E9 (loop counters, crash/resume, real audit on oracle maps, perturbed perceivers, fingerprint edits, mutants + own invariant baseline); removed Prop. 2 headline; rewrote RQs; Table 1 rebuilt (CYC/SAFE/GT dropped); bib fixed, 5 web a11y/DAST sources added; internal wording removed; 20 pages, 0 overfull, 1 OT1 font warning; E1-E4 JSON values verified identical | resolved 12 of 18 outright; partial F-03, F-11, F-17, F-18, F-13; blocked F-14 | 6.9 (audit 2) |
| v3 | 2026-10-09 | E10 XPath baseline, E11 two-seed variant, per-family RQ5, Table 1 re-read (axe marquee, ZAP spider), bib pages, system/model wording fixes, Discussion/Conclusion trimmed; 20 pages, 0 overfull, 1 OT1 warning, abstract 141 words | see 9c | 7.5 (audit 3) |
| v4 | 2026-10-09 | E12 three extra apps (pre-registered truth), E13 per-variant renames, E11 hash-seed fix, LangGraph citation, A8 wording, Table 1 AXNav/MATE notes, bib fixes, figure removed; 20 pages, abstract 146 | see 9d | 7.5 (audit 3) |

## 9b. Corrections to earlier memory
- Sect. 5 "excluded" loop counters are now REPRODUCED by run_experiments.py (E5): 11 pairs, 0 dup, 9 replays, 21 steps, 6 revisit edges, frontier_exhausted (authorised by orchestrator).
- V-03 is three actions from seed (depth 3), not two.
- DOM arm: V-04 hit is coincidental; genuine TP = 1 (A3), 2 (E4).
- E5 finding (Track B relevant): graph_runner resume re-runs `act` without consulting the claim set, so the in-flight pair is re-attempted (11/11 positions); apps/ untouched.
- Bib verification this session (Crossref/fetch): see references.bib header; unverified remainder listed there. Pending with user: four "college references" (not added).
- New experiment keys in experiments.json: E5_loop, E6_real_audit_on_oracle_maps, E7_perturbed_perceivers, E8_fingerprint_edits, E9_mutants_and_baseline, meta.

## 9c. Audit 2 (score 6.9, Borderline) status after v3
Details: audit/revision-matrix-03.md. F-19, F-20, F-22, F-23, F-25, F-26 resolved; F-11/F-21 partial (MATE "?"); F-03 partial (A8 independent XPath baseline added; extra subjects and real Crawljax/ATUSA blocked); F-14 blocked (Track C); F-17 resolved for restatements; F-18/F-24 partial (artifact not committed/archived; four "college references" pending with user, NOT added).
New keys: E10_xpath_baseline (68 variants by family, A8 exact on 64 shape-preserving, loses on 4 label renames: 4 FN_F, 10 FP_R; A2 on stripped fixture P0.17 R0.25), E11_two_seed_variant (13 pairs, restart continues via unclaimed seed action), key_map. Old keys verified identical.

## 9d. Audit 3 (7.5) status after v4
Details: audit/revision-matrix-04.md. F-27, F-28, F-29, F-30, F-31, F-25-residual resolved; F-32 partial (MATE "?"); F-03 partial (independence blocked); F-14 blocked; F-17 resolved for restatements; F-18/F-24 partial (artifact uncommitted).

## 11. Immutable Constraints
- The exploration graph is CYCLIC; never "DAG"; never prune back-edges; loop prevention = visited (state_id, action_id) set only.
- RQ1 is on FakePerception + scripted crawler: never present as end-to-end.
- `click` is replay-safe as stated; keep that statement precise.
- Only report numbers in data/experiments.json or reproducible by run_experiments.py.
- Do not invent citations/results/datasets; do not claim plagiarism-free.
- Authors: Kavinraj S, Harshita R, Sanjay A R, Jai Subiksha T (Amrita Vishwa Vidyapeetham, Coimbatore); corresponding-author email supplied by the user and set in main.tex until supplied. Do not modify svproc.cls. Write only under docs/report/springer/.

## 12. Current status (after rev. 6, final writer pass)
- Authors: Kavinraj S, Harshita R, Sanjay A R, Jai Subiksha T; Amrita Vishwa Vidyapeetham, Coimbatore; corresponding-author email supplied by the user and set only in main.tex. Nothing committed (user instruction).
- Paper: 22 pages, abstract 147 words, 0 overfull, 0 undefined, bibtex 0 warnings, 1 OT1 font warning, no placeholder text. references.bib: 52 entries (48 + 4 college references).
- College references: #1 CPE 37(15-17) e70151 and #3 ICICV 2020 pp.392-400 and #4 JCTN 17(1) 308-315 matched Crossref metadata (no abstracts read). #2: supplied form said 2025/et al.; the user chose the Crossref form (five authors, 2026, pp. 373-386, DOI 10.1007/978-981-96-9716-8_29); LNEE vol. 1459 and the "Proceedings of PEIS 2025, Volume 1" title come from the user, unverified. #3/#4 cited in one sentence by title and venue only; #1/#2 in a neutral Acknowledgments note. No relevance claims.
- Evidence: E1-E14 in experiments.json (E14: four generated apps; invariants hash recorded; ordering self-attested; fixtures weak and untracked). No independent subject, no browser/VLM result, no real Crawljax/ATUSA baseline.
- Still blocked: Track C vocabulary and Gemini identifier (F-14), artifact commit/archive, MATE "?" cells, venue page limit, similarity check.
- Audits: 5.7, 6.9, 7.5, 7.8, 7.8. Revision rows v5 (E14, F-33/34, authors, college refs) and v6 (F-35, F-38..F-43 wording). Matrices: audit/revision-matrix-02..06.md.
