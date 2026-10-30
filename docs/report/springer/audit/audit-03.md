# Audit report: StateScout Springer paper (iteration 3 of 4)

I wrote no repo files. The re-run, compile copy, shingle scripts and fetches are all in the session scratchpad. `git status` at the repo root shows only the pre-existing entries: the staged `.claude/hooks/track_b_paths.py` and the untracked `.claude/agents/*` and `docs/report/`. Nothing under `apps/`, `tests/`, `test-apps/`, `services/` or `infra/` changed. I loaded `run_experiments.py` as a module and called the `e*()` functions in-process. I never called `main()` and wrote nothing to `data/`.

## 1. Executive verdict

- **Overall score: 7.5 / 10** (audit 2: 6.9; audit 1: 5.7). Threshold 8.0 is not met.
- **Recommendation: Major Revision**, now close to Minor for a fixture-level workshop paper.
- **Publication readiness: Borderline.**

Seven of the writer's eight claims are confirmed. The eighth, F-03 partial, needs qualification (F-27 below). The paper is now honest and internally consistent. The score is held down by evidence breadth, not by prose.

**Three most serious problems**
1. **F-03 (High, partial).** There is still effectively one subject application. A8 is a real step, because it does not read `data-tag`. It was written with the fixture's label texts in view and the mutator inserts those same labels, so on the 64 shape-preserving mutants it cannot lose, and the paper says so. The only evidence that it can fail is 4 renames, which the writer chose.
2. **F-27 (Medium, new).** The paper says further subject applications "were not available". Three more apps already sit in the repo: `test-apps/broken-rbac-demo`, `missing-consent-demo` and `broken-feature-flag-demo`. They are unannotated (no `data-tag`), have documented defects in their READMEs and no ground-truth JSON, and git shows at least two of them were committed by a different team member. The statement is inaccurate as written. In audit 2 I also overlooked these apps, which is my miss. They are the cheapest route to a second subject.
3. **No browser-driven, VLM or hybrid result (blocked).** The abstract is honest about this, but it caps the evidence and technical scores.

**Checks that passed**
- E1_E3, E2, E5 to E9, E10, E11 and key_map reproduce the stored JSON exactly in-process. E1 to E9 and meta are also identical to my saved v2 snapshot, so the writer's "identical" claim holds.
- Compiled in a scratch copy: 20 pages (16 body, 4 references), 0 overfull boxes, no undefined references, one OT1 small-caps font warning.
- The abstract is 141 words.
- `svproc.cls` is byte-identical to the copy in `Latextemplate.zip`. `amsthm` is not loaded.
- All 47 bib entries are cited and none is missing.
- No leaks ("track", "college", "novelty analysis") appear in the PDF text. The graph is called cyclic throughout.

## 2. Verification of the writer's claims

| Claim | Result |
|---|---|
| F-19 resolved | **Agree.** `system.tex:41-44` says the checkpoint holds frontier, order, skips and counters, and the claim set is in the graph store. This matches `ExplorationState` and `scan` (`graph_runner.py:178` consults `is_visited` only in scan). |
| F-20 resolved | **Agree, with caveat.** Reported per family and "at scale" is gone. Counts are called non-independent. Table 7 figures match `E10.families` cell by cell. |
| F-22 resolved | **Agree.** E11's claims are supported by the code (section 3 below). |
| F-23 resolved | **Agree.** D is stated as the observed depth 3, with the configured limit of 10. |
| F-25 resolved | **Agree.** Five added page ranges match Crossref: Stoat 245–256, WebMate 55–69, Yandrapally 186–197, nl2spec 383–396, NL2LTL 16428–16430 (vol 37, issue 13). The Trident rename is correct (arXiv v2, 4 Dec 2024). The grounding claim is now attributed to SeeAct, whose abstract says grounding "remains a major challenge". |
| F-26 resolved | **Agree.** The text now reads "a Gemini Flash model". |
| F-17 resolved | **Agree for restatements.** The page limit is still unknown. |
| F-03 partial | **Agree**, but see F-27. |
| F-11/F-21 partial | **Agree.** MATE "?" remains and is honestly captioned. |
| F-18/F-24 partial | **Agree.** The paper says the script and JSON are uncommitted, with no archive. The key map exists. |
| F-14 blocked | **Agree.** Needs Track C. |
| E1–E9 identical | **Verified**, against both the stored JSON and the v2 snapshot. |

### (1) A8: independence, tuning, over- and under-selling

- **What is independent.** A8 genuinely does not read `data-tag`. The four XPaths are `.//a[.='Admin']`, `.//section[h2='Debug']`, `.//button[.='Delete user']` and `.//a[@href='#main'][.='Skip to content']`. Stripping the tags leaves A8's fixture scores identical (P 1.0, R 1.0), and its per-family results are unchanged on the stripped copies.
- **Not independent of the mutator's labels.** The mutator's snippets and A8 use the same label strings. The writer writes "That success is not independent evidence either", which is correct.
- **It can lose, but the losing cases were selected.** The label renames lose exactly as claimed: 4 FN_F and 10 FP_R. These renames were added in revision 3, so the losing cases are authored, not found.
- **Tuning.** I cannot verify "written once ... not tuned afterwards". The artifact is untracked and has no history, so this is an unverifiable authorial claim. It is at least consistent with the rename family having been added afterwards.
- **Selling.** The core framing is honest: "each encoding thus fails where the other does not, and neither is an independent oracle". Four small points:
  - "Over roles and visible text" is imprecise. No ARIA `role` attribute is used. The queries use element types, a link target and text (F-29).
  - Leading with "A2 collapses on the stripped fixture" (P 0.17, R 0.25) is close to a tautology. It strips the annotation that the oracle perceiver reads. The informative comparison is A3 against A8 on the same pages: A3 has 2 TP and 5 FP, A8 has 4/0. A 13-line label script beats the shipped DOM channel here. The paper implies this but never says it plainly (F-30).
  - The 4 renames are really 3 independent ones, because the "all three" variant double-counts the singles. The totals 4 FN_F and 10 FP_R therefore double-count.
  - "13 lines for A8" excludes the roughly 28-line HTML parser helper. This understates script effort, so it errs against the paper's own side.

### (2) E11 against the code: supported

- **Checkpoint results.** Two-seed variant (7 states, 13 pairs): 13/13 positions re-attempt the in-flight pair after a crash at the claim, and 0/13 after an edge-write crash. This follows from `act` re-running without consulting the claim set.
- **Claim-set restart.** Only the unclaimed seed action continues, because `scan` filters on `is_visited` at the seed. A crash at claim 1 gives 2 pairs (About, then Home). From claim 2 on, both seed actions are claimed, so 0 pairs run and 1 to 12 of 13 edges are persisted. The paper says exactly this.
- **Defect in the artifact.** The row field `second_run_attempts_of_claimed_pairs` slices `list(graph.visited)`, which is a set (F-31). Under `PYTHONHASHSEED=3`, E11 differs from the stored JSON in that single field: row 1 gives 0 instead of 1. Seeds 1, 2, 4 and 5 and the default match. Every number the paper reports is stable, and the paper does not cite this field. It is still a reproducibility blemish.
- **Missing citation.** LangGraph's documentation says a resumed node restarts from its beginning and side effects must be idempotent. E5's mechanism is therefore the framework's documented behaviour. The paper frames it only as contradicting the project's own intent, which is accurate, but it should cite the documentation (F-28).

### (3) Table 1 cells re-verified

- **axe-core NEG ✓.** The `marquee` rule reads "`<marquee>` elements must not be present". Verified.
- **ZAP AE ✓.** The spider "visits these URLs ... adds them to the list of URLs to visit ... recursively". It is link-following, so "autonomous exploration" is liberal but defensible.
- **AXNav REQ "--".** Defensible, but the abstract names heuristics such as "text size not increasing with Large Text enabled" and "VoiceOver navigation loops". That is a must-hold behavioural check. "Not stated in what we read" is slightly generous (F-32, Low).
- **MATE "?".** I could not fetch the abstract either. The writer's "?" is honest.

### (4) Bibliography: cumulative coverage

About 43 of 47 entries are now checked at some level. New this round:
- **Crossref DOI match:** five new page ranges plus Sapienz, DroidBot, MACE, Crawljax and ATUSA.
- **Fetched or search-confirmed:**
  - ARO: ICLR 2023 oral, authors match.
  - CREPE: CVPR 2023, pp. 10910–10921, authors match.
  - Mind2Web: NeurIPS 2023 spotlight, authors match.
  - OSWorld: 17 authors match.
  - WebArena: 12 authors match.
  - SeeAct: authors match.
  - VisionDroid: the abstract says Trident, and v1 is dated 3 Jul 2024.
- **Still unverified:** Noseevich and Petukhov pages 11–18; Memon 2003 pages; MATE contents; the venue years for WebArena and OSWorld (the arXiv pages did not show them); full texts other than ATUSA.
- **Attribution.** WebArena, Mind2Web and OSWorld are described as benchmarks, which is correct. No misattribution found.
- **New BibTeX warning** (F-31): "can't use both volume and number" for `fuggitti2023nl2ltl`. The printed entry drops the issue. This was introduced in v3 when `number` was added.

### (5) Compile and integrity

See the checks listed in section 1. The `make` flow also leaves the committed `main.pdf` at 20 pages.

### (6) git

Nothing outside `docs/report/` changed apart from the pre-existing `.claude` entries. No `.pyc` files newer than the revision matrix were found under `apps/` or `tests/`.

### (7) New slips, working-note text, overclaims

- No working-note text was found in the PDF, apart from the odd phrase "A8 by someone who had seen the label texts" (F-29).
- The claim that further subject apps "were not available" is inaccurate (F-27).
- Intro: "nobody scripts a scenario for a button that should not exist" is an uncited generalisation (Low).
- Abstract, intro and conclusion are properly scoped to fixture level. I found no overclaim.
- `MEMORY.md` sections 3 to 8 are stale and contradict its own section 9b. Examples: "Hardware/software versions: not recorded", "This session did NOT re-run the script", "Proposition 2", "19 pages". It is a working file and not part of the paper, but it should not be trusted as a status source.
- The script docstring still says "Prop. 2" and lists E10 and E11 before E9.

## 3. Detailed scoring and audit trail vs 6.9

| Criterion | Score | Max | Change | Justification |
|---|---:|---:|---:|---|
| Novelty and originality | 1.0 | 2.0 | 0 | The contribution is still a thin formulation: a typed polarity field, a role scope and a vocabulary. Positioning is accurate, and Table 1 is more precise (axe marquee, ZAP spider). That is not new novelty. |
| Technical correctness and methodology | 1.65 | 2.0 | +0.15 | F-19, F-22 and F-23 are fixed and E11 is code-grounded. Deductions: the A8 "roles" wording, the unverifiable "not tuned" claim, the E5 mechanism not tied to LangGraph's documented semantics, and the nondeterministic E11 field. |
| Evidence, experiments, results | 1.4 | 2.0 | +0.2 | E10 adds a partially independent baseline with honest framing, E11 supports the generalisation, and results are now per family. Still capped by one subject, author-selected losing cases, n=4 renames (3 independent) and no browser or VLM result. |
| Literature and citation quality | 1.3 | 1.5 | +0.1 | F-21 and F-25 are resolved. About 43 of 47 entries are checked and there is no fabrication. Left open: MATE "?", Noseevich pages, the LangGraph documentation citation. |
| Structure, reasoning, coherence | 0.9 | 1.0 | +0.1 | The working note and restatements are gone and limitations are consolidated. The 20-page length is unjustified until the limit is known. |
| Reproducibility and limitations | 0.85 | 1.0 | +0.05 | The key map and honest artifact statement are good. The artifact is still untracked and unarchived, and one stored field is hash-seed dependent. |
| Academic writing and presentation | 0.4 | 0.5 | 0 | Fluent and precise. A few impersonal phrases remain. |
| **Total** | **7.5** | **10.0** | **+0.6** | |

**Audit trail**
- Technical +0.15: F-19, F-22 and F-23 are verified fixed. New Low issues F-28, F-29 and F-31 offset part of the gain.
- Evidence +0.2: E10 and E11 verified. Raised only for new, reproducible, honestly framed results. Not raised for length.
- Literature +0.1: seven more entries verified and five page ranges confirmed. F-27, F-28 and F-32 remain.
- Structure +0.1: F-26 resolved and restatements cut. Page limit unknown.
- Reproducibility +0.05: key map added. Artifact still untracked.
- Novelty and writing: no change.
- No criterion rose because of length. The paper stayed at 20 pages.

## 4. Critical findings

**Earlier findings: status as verified**
- **Resolved:** F-01, F-02 (at fake level), F-04 to F-10, F-12, F-13, F-15, F-16, F-17 (restatements), F-19, F-20, F-22, F-23, F-25, F-26.
- **Partial:** F-03, F-11/F-21, F-18/F-24.
- **Blocked:** F-14.

**New findings**
- **F-27, Medium. `evaluation.tex` Threats (§5.7); `discussion.tex` last paragraph.**
  - Evidence: "Further subject applications ... were not available". `test-apps/` holds `broken-rbac-demo` (multi-page, with a link labelled "Admin Dashboard (Violation)"), `missing-consent-demo` (a required-absent defect) and `broken-feature-flag-demo` (an "Export Data" button). None uses `data-tag`. Each README documents one defect, and none has `app.json`, `policy.json` or `violations.json`. Git shows a second committer on at least two of them. Crawler tests already reference two of them.
  - Why it matters: a different-vocabulary, unannotated subject is exactly what the DOM channel and A8 need to be tested against.
  - Correction: either evaluate them or state precisely why not.
    - Evaluate: structure each policy from the README's English sentence (in memory, ground truth from the README) and run A3 and A8. Report per app and state that the apps come from the same project.
    - Otherwise reword to "no ground-truth files exist".
- **F-28, Low to Medium. `evaluation.tex` Crash and resume; `discussion.tex`.** Cite LangGraph's durable-execution documentation. Say that node re-run on resume is documented framework behaviour, and that the finding is the gap between that and the project's intended claim-handling. A web search surfaced a 2026 preprint on resume contracts that I did not read. It is a lead only and not verified.
- **F-29, Low. `evaluation.tex` RQ5; Table 2.** Replace "roles, visible text" with "element types, link targets, visible text". Replace "by someone who had seen the label texts" with a plain statement that the authors knew the labels. Soften or drop "not tuned afterwards", or qualify it as an unverifiable authorial statement. Say the 13 lines exclude the shared parser.
- **F-30, Low. `evaluation.tex` RQ5; Table 7.**
  - Add a plain sentence that on this fixture a label-based script beats A3 on the stripped copies.
  - Present A2s as "oracle perceiver without its annotations", not as a competitor.
  - Report the 4 renames per variant, because "all three" double-counts the singles.
- **F-31, Low. Artifact.**
  - In `run_experiments.py`, snapshot `graph.visited` before the second run so `second_run_attempts_of_claimed_pairs` stops depending on `PYTHONHASHSEED`.
  - Fix the `fuggitti2023nl2ltl` volume and number warning.
  - Correct the docstring ("Prop. 2" and the E10, E11 order).
  - Refresh or retire the stale `MEMORY.md` sections 3 to 8.
  - Commit the artifact (an author decision).
- **F-32, Low. Table 1.** MATE "?" remains. The AXNav REQ caption is slightly generous (see section 2, point 3).
- **Residual.** Noseevich pages 11 to 18 are unverified. The intro's "nobody scripts a scenario" sentence needs a citation or hedge.

## 5. Integrity assessment

**Plagiarism evidence.** No similarity corpus was available, so comprehensive verification was not performed. This is not a plagiarism-free verdict.

8-word shingles vs the `paper/` and `ieee/` drafts (same method as audit 2):

| Section | Strict (audit 2) | Strict now | Loose now |
|---|---:|---:|---:|
| introduction | 0.054 | 0.055 | 0.060 |
| related | 0.023 | 0.021 | 0.023 |
| model | 0.101 | 0.101 | 0.142 |
| system | 0.056 | 0.056 | 0.060 |
| evaluation | 0.003 | 0.003 | 0.006 |
| discussion | 0.052 | 0.037 | 0.041 |
| conclusion | 0.062 | 0.027 | 0.026 |
| abstract | 0.014 | 0.014 | 0.013 |
| overall | about 0.038 | 0.033 | 0.043 |

- `model` is still the highest section, from reused definitions. `evaluation`, the section rewritten most, is essentially new text.
- **Against `novelty-analysis.md`:** strict 8-word shingles give 0 in every section. The loose pass gives 4 in related (the Table 1 column definitions NEG, REQ and ROLE) and 5 in evaluation (the policy-subject list). Strict 7-word shingles give 1 in introduction and 1 in related. Loose 7-word shingles give 1 in introduction, 5 in related and 7 in evaluation. All are vocabulary overlaps.
- **External spot checks:** six distinctive sentences from evaluation, related and system were searched as exact phrases. There were no matches. I also fetched the abstracts of AXNav, SeeAct, ARO, Mind2Web, OSWorld, WebArena and VisionDroid, plus the ZAP spider and axe `marquee` pages. No unattributed borrowing or citation laundering was found.
- **Not verified:** full texts of cited works (except ATUSA, checked in audit 2) and the web at large.

**Citation integrity.** About 43 of 47 entries were checked. No fabrication or misattribution was found. See section 2, point 4 for what remains unverified.

**AI-style risk: Low to Medium (Indeterminate beyond that).**
- Evidence for the risk: uniform, polished prose and formulaic hedges. Evidence against it: precise, checkable specifics, negative results kept (E5, E8, A8's losses), and numbers that trace to the JSON.
- Limitation: style does not establish authorship, and a drafting agent is documented in the repo.

**External detector results:** none provided, so none reported.

**Verification limitations.** I did not run `pytest`. I did not run the live Playwright, VLM, Neo4j or Redis pipeline. I did not compile in place. Prior-art completeness cannot be established by search.

## 6. Revision plan (ranked)

1. **New experiments, no repo edits** (F-27, F-03). Add the three in-repo apps as in-memory subjects. For each, derive policy and ground truth from its README. Run A3 (the unannotated DOM channel) and an A8-style XPath script written before looking at results. Report per app, state authorship honestly, and keep the claims fixture-level. These apps are small, so do not call this independent validation.
2. **Factual and wording corrections:** F-29, F-30, F-28.
3. **Source verification:** F-32 (MATE and AXNav cells), Noseevich pages, the LangGraph documentation citation.
4. **Artifact hygiene:** F-31.
5. **Structural:** page-limit decision once the venue is known (author).
6. **Stylistic:** cite or hedge the "nobody scripts" sentence.

## 7. What is reachable and what blocks 8.0

- **Realistic ceiling in the remaining iteration: about 7.7 to 7.9.** The extra-subject runs could raise evidence to about 1.55 to 1.6. Technical could reach 1.75 and literature 1.35. Structure and reproducibility could each gain about 0.05 if the artifact is committed. This estimate assumes the new numbers are stored and reproducible.
- **8.0 is borderline reachable only if everything lands.** It needs the three-app evaluation executed and honestly reported, F-28 to F-32 cleanly fixed, MATE settled, and the artifact committed.
- **What exactly blocks 8.0:**
  - **Evidence breadth.** Even the three apps are same-project, tiny and single-defect. A genuinely independent subject, preferably open-source with real defects, plus a real Crawljax and ATUSA baseline, is still required for a firm 8.0 or more. That is an author and orchestrator decision.
  - **No browser, VLM or hybrid result.** It is blocked by the Track C vocabulary decision and the API key.
  - **Novelty.** Capped near 1.1. The contribution is a small formulation, and prose cannot change that.
  - **Process blocks.** The Gemini identifier mismatch (F-14), the unarchived artifact (F-18), and the unknown venue and page limit.
- **My earlier ceiling.** In audit 2 I said 8.0 needed new subject apps. I missed that three exist in the repo, so a smaller route to partial independence is available than I stated.

## 8. Writer handoff (machine-readable)

```json
{
  "audit_iteration": 3,
  "iteration_limit": 4,
  "remaining_iterations_after_this": 1,
  "quality_threshold": 8.0,
  "target_venue": "Springer svproc proceedings (software engineering / AI agents); no named venue; page limit unknown",
  "paper_source": {
    "immutable_reference": "docs/report/springer/main.tex + sections/{introduction,related,model,system,evaluation,discussion,conclusion}.tex + references.bib at audit 3 (20 pages: 16 body, 4 references); data docs/report/data/experiments.json (E1_E3,E2,E5-E11,key_map reproduce IDENTICAL in-process; E1-E9 and meta identical to v2 snapshot; E11 field second_run_attempts_of_claimed_pairs is PYTHONHASHSEED-dependent); script docs/report/experiments/run_experiments.py",
    "write_scope": "docs/report/springer/ plus docs/report/data/ and docs/report/experiments/ only for authorised new experiments; never touch apps/, tests/, test-apps/, services/, infra/, svproc.cls, .claude/"
  },
  "required_format": {
    "class": "svproc (unmodified, byte-identical to Latextemplate.zip); \\mainmatter; abstract 70-150 words (now 141); bibliographystyle plain + natbib numeric; packages allowed: url helvet courier graphicx multirow booktabs amsmath amssymb natbib tikz; forbidden: amsthm, modifying svproc.cls; captions: tables above, figures below"
  },
  "current_score": {
    "overall": 7.5,
    "previous": 6.9,
    "breakdown": {
      "novelty_originality": {"score": 1.0, "max": 2.0, "delta": 0.0},
      "technical_correctness": {"score": 1.65, "max": 2.0, "delta": 0.15},
      "evidence_results": {"score": 1.4, "max": 2.0, "delta": 0.2},
      "literature_citations": {"score": 1.3, "max": 1.5, "delta": 0.1},
      "structure_coherence": {"score": 0.9, "max": 1.0, "delta": 0.1},
      "reproducibility_limitations": {"score": 0.85, "max": 1.0, "delta": 0.05},
      "writing_presentation": {"score": 0.4, "max": 0.5, "delta": 0.0}
    },
    "recommendation": "Major Revision",
    "readiness": "Borderline",
    "realistic_ceiling_next_iteration": "7.7-7.9; 8.0 only if three-app evaluation lands AND F-28..F-32 fixed AND MATE settled AND artifact committed; firm 8.0+ needs a truly independent subject, real Crawljax+ATUSA baseline and/or a browser-driven result"
  },
  "resolved_and_verified": [
    "F-01","F-02 (fake level)","F-04","F-05","F-06","F-07","F-08 (E7 is an engine unit test)","F-09","F-10","F-12","F-13","F-15","F-16",
    "F-17 (restatements; page limit unknown)","F-19","F-20 (per family; counts non-independent)","F-22 (E11 supported by graph_runner.scan/act)","F-23","F-25 (5 page ranges Crossref-confirmed; Trident; SeeAct grounding)","F-26"
  ],
  "findings": [
    {"id": "F-03", "severity": "High", "status": "partial", "location": "evaluation.tex RQ5, threats; abstract",
     "evidence": "A8 is independent of data-tag but written knowing fixture labels and the mutator inserts the same labels; the only losing cases are 4 author-chosen label renames; single subject; same authors for app, tool, mutators, baselines",
     "correction": "Add independent-subject evidence per F-27; keep fixture-level claims and the 'own re-implementation, not ATUSA' label",
     "blocked_part": "genuinely independent subject apps and a real Crawljax+ATUSA baseline need author/orchestrator approval"},
    {"id": "F-27", "severity": "Medium", "status": "open", "location": "evaluation.tex Threats (External); discussion.tex 'Scope, replay safety and what is missing'",
     "evidence": "Text says further subject applications were not available; test-apps/ contains broken-rbac-demo, missing-consent-demo, broken-feature-flag-demo (no data-tag; README-documented defects; no app.json/policy.json/violations.json; at least two committed by a different team member; crawler tests reference two)",
     "correction": "In memory only: derive a structured policy and ground-truth triples for each app from its README sentence; run A3 and an XPath script written before results are seen; store results in experiments.json under a new key with a key_map entry; report per app; disclose same-project authorship and that apps are tiny. If not run, replace 'not available' with the precise reason (no ground-truth files). Do not edit test-apps/."},
    {"id": "F-28", "severity": "Low-Medium", "status": "open", "location": "evaluation.tex Crash and resume; discussion.tex Resuming safely",
     "evidence": "LangGraph durable-execution docs: a resumed node restarts from its beginning and side effects must be idempotent; E5 mechanism is documented framework behaviour",
     "correction": "Cite the LangGraph durable-execution documentation (add a bib entry with access date); frame E5 as the gap between that behaviour and the intended claim handling. Do not cite the resume-contract preprint unless read and verified."},
    {"id": "F-29", "severity": "Low", "status": "open", "location": "evaluation.tex RQ5 and Table 2; threats",
     "evidence": "A8 queries use element types, a link target and text, not ARIA roles; 'written once ... not tuned' is unverifiable; 'by someone who had seen the label texts' is evasive; 13 lines exclude the ~28-line parser helper",
     "correction": "Describe A8 as element types, link targets and visible text; state authors knew the labels; qualify or drop 'not tuned'; say '13 lines of invariants plus a shared HTML parser'"},
    {"id": "F-30", "severity": "Low", "status": "open", "location": "evaluation.tex RQ5; Table 7",
     "evidence": "A2-on-stripped 'collapse' is near-tautological; informative comparison is A3 vs A8 on stripped pages (A3 2 TP/5 FP vs A8 4/0); 'all three' rename double-counts the singles so 4/10 is not 4 independent items",
     "correction": "State plainly that on this fixture a 13-line label script beats the shipped DOM channel; present A2s as an annotation-free oracle perceiver; report the 4 renames per variant"},
    {"id": "F-31", "severity": "Low", "status": "open", "location": "run_experiments.py e11/_claim_set_restart; references.bib fuggitti2023nl2ltl; script docstring; MEMORY.md",
     "evidence": "second_run_attempts_of_claimed_pairs slices list(set); under PYTHONHASHSEED=3 E11 row 1 gives 0 vs stored 1 (reported paper numbers stable across seeds 1-5); BibTeX warning 'can't use both volume and number'; docstring says Prop. 2 and lists E10/E11 before E9; MEMORY.md sections 3-8 stale",
     "correction": "Snapshot the claimed set before the second run and re-store E11; put number in note or drop it; fix docstring; refresh MEMORY.md; commit the artifact if authors agree (F-18/F-24)"},
    {"id": "F-32", "severity": "Low", "status": "open", "location": "related.tex Table 1 (MATE, AXNav)",
     "evidence": "MATE NEG/REQ still '?'; AXNav abstract names 'text size not increasing' as a heuristic, a must-hold check, so 'not stated' is slightly generous",
     "correction": "Settle MATE from a fetched source or leave '?' with reason; consider '~' or an explanatory note for AXNav REQ"},
    {"id": "F-11/F-21", "severity": "Medium", "status": "partial", "location": "related.tex Table 1",
     "evidence": "axe NEG and ZAP AE verified; MATE '?' remains", "correction": "See F-32"},
    {"id": "F-14", "severity": "Medium", "status": "blocked", "location": "system.tex Perception",
     "evidence": "gemini.py docstring says 2.5 Flash; _MODEL='gemini-3.6-flash'", "correction": "Keep 'a Gemini Flash model'; Track C reconciles"},
    {"id": "F-18/F-24", "severity": "Low", "status": "partial", "location": "artifact",
     "evidence": "docs/report untracked; no archive; cited commit 4487574 predates script and JSON; key map present", "correction": "Commit/tag/archive is an author decision"},
    {"id": "F-17", "severity": "Low", "status": "partial", "location": "whole paper", "evidence": "20 pages; limit unknown", "correction": "Fit venue limit when known"},
    {"id": "F-25-residual", "severity": "Low", "status": "open", "location": "references.bib noseevich2011detecting; introduction.tex first paragraph of para 2",
     "evidence": "Noseevich pages 11-18 unverified; 'nobody scripts a scenario for a button that should not exist' is an uncited generalisation", "correction": "Verify the pages or omit; add a citation or hedge"}
  ],
  "must_not_change": [
    "The exploration graph is CYCLIC; never call it a DAG; never prune revisit/back edges; loop prevention = visited (state_id, action_id) set only",
    "RQ1/RQ3 use FakePerception and a scripted crawler; never present as end-to-end",
    "REPLAY_SAFE_KINDS = {navigate, click, back}; click is replay-safe; keep the residual-risk statement",
    "Only report numbers present in data/experiments.json or reproduced by run_experiments.py; any new experiment must be authorised, stored, and reproduce from the script",
    "Do not edit E1-E11 values to improve results; keep the E5 negative result, E8 over-merge findings and A8's losing cases",
    "Do not edit anything under test-apps/; build new subjects in memory only",
    "Keep the disclosures: oracle arms read data-tag; A6 and A8 are our own re-implementations, not Crawljax/ATUSA; no browser/Neo4j/Redis; A4 post hoc",
    "Do not invent citations, results or detector scores; do not claim plagiarism-free",
    "Authors remain placeholders; do not modify svproc.cls; do not load amsthm; abstract <=150 words",
    "Keep 'formalise and combine' scoping; do not claim first crawler, novel cyclic graph, novel fingerprint, OWASP A01 detection, NL-policy-driven audit or solved VLM negation",
    "Do not add the four 'college references' unless the user decides; do not penalise their absence",
    "Do not change anything outside docs/report/"
  ],
  "blocked_by_missing_evidence": [
    {"item": "Truly independent subject apps and real Crawljax+ATUSA baseline (F-03)", "needed": "Author/orchestrator approval and apps"},
    {"item": "End-to-end Playwright to semantic map to audit run", "needed": "Track C vocabulary decision and authorisation"},
    {"item": "Live Neo4j/Redis/durable-checkpointer crash test", "needed": "Infra and authorisation"},
    {"item": "VLM/hybrid per-polarity accuracy", "needed": "API key, wired channel, labelled probe set"},
    {"item": "Gemini model id mismatch (F-14)", "needed": "Track C"},
    {"item": "Archive/DOI and commit of the artifact (F-18/F-24)", "needed": "Author decision"},
    {"item": "Authors, venue, page limit", "needed": "Author decision"},
    {"item": "MATE and Noseevich details", "needed": "Reachable full text"},
    {"item": "Similarity corpus; AI-detector results", "needed": "None provided"}
  ],
  "unresolved_questions": [
    "Will the authors authorise evaluating the three in-repo test apps (policy and ground truth derived from their READMEs, in memory)?",
    "Venue page limit versus 20 pages?",
    "Should the E5 resume finding be filed with Track B?",
    "Should the artifact be committed and tagged?"
  ],
  "previous_iterations": [
    {"iteration": 1, "score": 5.7, "recommendation": "Major Revision"},
    {"iteration": 2, "score": 6.9, "recommendation": "Major Revision"}
  ],
  "iteration_budget": {"threshold": 8.0, "iterations_remaining_after_this": 1,
    "note": "Do F-27 evaluation first, then F-29..F-32, F-28, F-25-residual. Mark anything needing new apps, browser or author decisions as blocked and report honestly; do not endlessly rewrite prose."}
}
```

## Relevant files (all read-only)

- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/sections/evaluation.tex` (F-27, F-29, F-30)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/sections/related.tex` (F-32)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/sections/discussion.tex`
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/references.bib` (F-31, F-25 residual)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/experiments/run_experiments.py` (A8 at `XPATH_INVARIANTS`; E11 at `_claim_set_restart`)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/data/experiments.json`
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/MEMORY.md` (stale sections 3 to 8)
- `/home/kr95/Projects/final-year-project/statescout-ai/apps/agent/orchestrator/graph_runner.py` (scan line 178, act line 217)
- `/home/kr95/Projects/final-year-project/statescout-ai/test-apps/` (the three unused subjects)

Sources checked:
- [ZAP spider](https://www.zaproxy.org/docs/desktop/addons/spider/)
- [axe marquee rule](https://dequeuniversity.com/rules/axe/4.10/marquee)
- [AXNav, arXiv 2310.02424](https://arxiv.org/abs/2310.02424)
- [VisionDroid / Trident, arXiv 2407.03037](https://arxiv.org/abs/2407.03037)
- [ARO, arXiv 2210.01936](https://arxiv.org/abs/2210.01936)
- [Mind2Web, arXiv 2306.06070](https://arxiv.org/abs/2306.06070)
- [OSWorld, arXiv 2404.07972](https://arxiv.org/abs/2404.07972)
- [WebArena, arXiv 2307.13854](https://arxiv.org/abs/2307.13854)
- [SeeAct, arXiv 2401.01614](https://arxiv.org/abs/2401.01614)
- [CREPE, CVPR 2023](https://openaccess.thecvf.com/content/CVPR2023/html/Ma_CREPE_Can_Vision-Language_Foundation_Models_Reason_Compositionally_CVPR_2023_paper.html)
- [LangGraph durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)
- [MATE, ICST 2018](https://ieeexplore.ieee.org/document/8367041)