# Audit report: StateScout Springer paper (iteration 1 of 4)

Audited files: `docs/report/springer/main.tex`, `sections/*.tex` and `references.bib`.

## 1. Executive verdict

- **Overall score: 5.7 / 10.**
- **Recommendation: Major Revision.**
- **Publication readiness: Not Ready.**
- **Quality threshold: 8.0.** The paper cannot reach 8.0 by rewriting alone. Reaching it needs new evidence: a second subject application, a baseline, and an end-to-end or real-engine run. See section 9, which lists what is blocked on author or orchestrator decisions.

**Three most serious problems**
1. **The evidence cannot support the claims (F-01, F-02, F-03).**
   - The only subject is one six-page app with four planted defects. The authors wrote both the app and the tool.
   - The "oracle" arm (1.00/1.00/1.00) uses `FakePerception`'s own set algebra, and the fake reads the same `data-tag` encoding the ground truth was written in. It tests nothing about the production engine.
   - Half of RQ1, the cyclic and claim-before-execute loop (contribution 3), has no data in the paper.
2. **The headline "negation-safe" design claim contradicts the paper's own model (F-04).**
   - The paper says the VLM "never decides existence or absence". But policy subjects are tags and capabilities, and the VLM adds tags and capabilities.
   - So a VLM annotation error changes membership in Σ(v), which decides both clause types. The paper's own RQ2 shows the failure is in tagging, not in element existence.
3. **The RQ2 result is a vocabulary bug presented as a perception finding (F-05, F-06).**
   - P=0.29 and R=0.50 are an exact-match mismatch between `policy.json` subjects and tagger output.
   - The paper's own ablation removes it (P goes to 1.00). The ablation was designed after seeing the results and is run on the same four items.
   - Proposition 2 is a one-line monotonicity fact. It is stretched ("under-reporting relative to vocabulary") until it cannot fail. "Errors follow the predicted asymmetry" in the abstract is therefore close to a tautology.
   - The reported V-04 true positive is vacuous (F-06).

**Checks that passed**
- All table numbers match `data/experiments.json`. I re-ran `e1_e3()` and `e2()` in-process, without writing files, and the output is identical to the stored JSON.
- It compiles (`pdflatex`, `bibtex`, `pdflatex` ×2, in a scratch copy): 19 pages, with only an OT1 small-caps font-substitution warning. The abstract is 142 words and `svproc.cls` is unmodified. Only `booktabs`, `amssymb`, `tikz`, `multirow` and `amsmath` were added; there is no `amsthm`.
- The cyclic constraint is respected throughout. Nothing calls the graph a DAG or prunes back-edges. RQ1 is correctly flagged as non-end-to-end. `click` is correctly stated as replay-safe. Authors are placeholders.

## 2. Detailed scoring

| Criterion | Score | Max | Justification |
|---|---:|---:|---|
| Novelty and originality | 0.9 | 2.0 | The paper honestly scopes itself as "formalise and combine". But by its own admission the oracle adds no expressive power over ATUSA. The distinguishing features are a role filter, typed polarity and a vocabulary, which are thin. Proposition 2 is trivial. There is no empirical comparison with the one baseline that matters (Crawljax with ATUSA-style invariants). Web accessibility and DAST checkers that already assert required presence and forbidden artifacts are not discussed (F-12). |
| Technical correctness and methodology | 1.1 | 2.0 | The Proposition 1 sketch is plausible and matches the `explore.py` argument. But "at-most-once" holds only for frontier executions, while replay re-fires prefix actions. The "negation-safe" claim is internally contradicted (F-04). "Back-edge" is misused (F-09). The Section 3 claim that fingerprint failure modes are "measured" is overstated (F-10). |
| Evidence, experiments, results | 0.8 | 2.0 | n=1 app, 4 positives, no variance, and no baseline. RQ1/RQ3 are structurally tautological, which the paper partly admits. The exploration loop has no data. RQ4 compares against a strawman naive hash with noise the normaliser was built to remove. Table 3 is six identical rows. Credit: the numbers are exact and reproducible, and the disclosure of arm composition is good. |
| Literature and citation quality | 1.1 | 1.5 | 40 references, broad, with correct venues in the sample I checked. The paper marks the Table 1 cells as unfinished (F-11). Leftover bib notes print in the reference list (F-13). Several are preprints. Related work lacks web accessibility and DAST tooling. |
| Structure, reasoning, coherence | 0.7 | 1.0 | Clear sections and a logical flow. Internal project artefacts leak in ("perception track", "internal novelty analysis", "four sub-teams"). Limitations are repeated 4–5 times (Sections 4.5, 5, 6). The V-label scheme is inconsistent (F-15). |
| Reproducibility and limitations | 0.7 | 1.0 | The limitations are unusually candid. The script reproduces exactly. But no software or hardware versions are recorded. The Gemini model naming conflicts with the code (F-14). The artifact is a path inside the repo, with no DOI or archive. The lexical ablation is an in-process monkey-patch. |
| Academic writing and presentation | 0.4 | 0.5 | Fluent and precise. Some formulaic hedging, and the Fig. 1 caption describes dotted lines that the figure does not contain. |
| **Total** | **5.7** | **10.0** | |

## 3. Critical findings

**F-01 — Critical — Section 4.1 ("Artifacts"), Section 4.2 (RQ1), Table 2 row 1, abstract**
- **Evidence:** `run_experiments.py::run_audit` for arm "oracle" calls `fake.analyze` and then `fake.audit`, not `negation.audit.audit`. `FakePerception` reads the same `data-tag` attributes the ground truth was written from. A 1.00/1.00/1.00 result is therefore near-tautological.
- **Why it matters:** The sentence "this establishes that the clause algebra and the ground-truth encoding agree" overstates it. The production `audit()` is never exercised with correct perception. Doing that is a trivial change.
- **Required correction:**
  - (a) New experiment: feed the fake's oracle semantic maps (`fake.analyze`) to the real `negation.audit.audit`, add that as an arm, and report it. Keep the old arm labelled "fake's own algebra".
  - (b) Rewrite the RQ1 text and abstract to say exactly what each arm exercises.
  - If (a) is not done, RQ1 must be downgraded to "consistency check of the fixture" and the abstract sentence about the "oracle-perception audit" reworded.

**F-02 — Critical — Introduction contribution 3, Section 3.2, Section 4.2 (RQ1)**
- **Evidence:**
  - RQ1 asks whether "the exploration structure keeps the graph cyclic". The paper then says the loop counters "are not produced by the artifact released with this version and we do not repeat them here". Fig. 2 is "derived by inspection".
  - Proposition 1's "including across crash and resume" has no experiment.
  - `docs/demo_crawl.py` exists and uses the real loop with fakes. The earlier draft's counters came from it.
- **Why it matters:** Contribution 3 (cyclic, claim-before-execute, kind-restricted replay) is claimed but has zero measured support. RQ1 is half unanswered.
- **Required correction:**
  - New evidence: run `docs/demo_crawl.py`, or better, extend `run_experiments.py` so the counters land in `experiments.json` as an "E5". Report executed pairs, duplicate executions, replays, replayed steps, back-edges persisted, termination reason, and skipped pairs when a fill/submit is injected.
  - Add a resume test showing no re-execution after a simulated crash between claim and edge. Cite the test names that already exist (`test_live_crawl.py`, `test_ground_truth.py`).
  - If this is not done, delete RQ1's "keeps the graph cyclic" clause and demote contribution 3 to a design description.
  - The orchestrator must authorise using demo_crawl numbers (MEMORY.md says they are excluded pending a re-run).

**F-03 — Critical — Section 4 as a whole, Section 5, Section 6**
- **Evidence:** One static app, 6 pages, 4 planted defects, authors wrote both sides, single deterministic run, no variance. Precision 0.29 is 2 true positives out of 7 reports.
- **Why it matters:** P/R/F1 on 4 positives are anecdotes. "Planted-defect bias" and "vocabulary overfitting" are acknowledged but not mitigated. The paper cannot support even a mechanism-level claim beyond "the code runs".
- **Required correction:**
  - New evidence (blocked, see section 9): add at least 2–3 additional subjects, and/or mutants of `broken-admin`. Mutate by removing each planted defect, adding new ones of both polarities, reordering, and renaming ids. Report per-polarity counts across the mutants.
  - Add the Crawljax plus ATUSA-style-invariant baseline named in the paper's own conclusion. At minimum, a hand-written XPath/DOM-invariant script encoding the same four clauses, compared on spec effort and results.
  - Cut abstract and RQ claims to match what a toy fixture supports.

**F-04 — Critical — Introduction contribution 2, Section 2 ("LLM and VLM agents"), Section 3.4, Section 4.4 (system perception)**
- **Evidence:**
  - The text says "in SS it [the VLM] never decides existence or absence" and "decided by evidence that cannot be hallucinated".
  - It also says the VLM adds tags and capabilities to elements, and that policy subjects are tags, names and capabilities (Eqs. 1–2 test σ ∈ Σ(v)). The code confirms this: `gemini.py::_gemini_capabilities` adds `extra_capabilities`.
  - A hallucinated or missed capability changes Σ(v), flipping both forbidden-present and required-absent verdicts.
  - The paper's own RQ2 shows the failure sits in subject grounding, which is exactly the annotation step.
- **Why it matters:** The central design claim ("negation-safe division of labour") is not safe as described. The VLM's annotations can silently create or hide a violation. Proposition 2 applies directly to the annotation channel.
- **Required correction:**
  - Reword to the precise claim: the VLM cannot add or remove DOM/AX elements, but it can add tags and capabilities, so grounding errors remain and are classed by Proposition 2.
  - Remove "never decides existence/absence" and "cannot be hallucinated".
  - Mark the design as unevaluated (the paper already does this in one place). Make that consistent everywhere, including the introduction.
  - State which subject kinds (element name or ID versus VLM-derived capability) are VLM-dependent.

**F-05 — High — Abstract, Section 4.3 (RQ2), Section 6 (Discussion), Section 7 (Conclusion)**
- **Evidence:**
  - P=0.29 and R=0.50 arise because `policy.json` subjects (`admin-link`, `debug-panel`, `skip-to-content`) never equal tagger output (`admin`, `debug`, none for skip). The lexical ablation then gets P=1.00. The two remaining misses (V-01, V-02) arise because the tagger emits `admin`/`debug` tags while the policy subjects are `admin-link`/`debug-panel`.
  - The ablation was designed after seeing the error list (the E4 docstring says so), on the same four items.
  - The abstract headlines these figures as if they were perception-quality findings.
- **Why it matters:** This is a configuration or integration inconsistency in the authors' own system, not evidence about perception. It is post-hoc, and one can fix it by renaming policy subjects.
- **Required correction:**
  - Reframe RQ2 as a case study of vocabulary-mismatch failure, not a perception-accuracy measurement.
  - Move the numeric P/R out of the abstract, or state in the abstract that they reflect a policy-tagger vocabulary mismatch.
  - Say that E4 is exploratory and post-hoc.
  - Note that the Track C decision (rename subjects or read `data-tag`) is an unresolved project decision. Consider running the fixed-vocabulary case, if the orchestrator authorises it, as a legitimate experiment.

**F-06 — High — Section 4.3 ("it finds two (V-03 and V-04)"), Table 2**
- **Evidence:**
  - In the DOM arm the skip-to-content clause is never recognised on any page, so `required_absent` fires on all six pages. The data confirms this: 5 false positives on index, dashboard, login, register and reports, plus the true positive on admin. The "V-04 found" credit is a coincidence of the fault, not detection of the missing link.
  - V-04 is only genuinely found in the E4 arm.
- **Why it matters:** The paper says the channel "finds two" violations and "V-03 is still found". The V-04 hit is vacuous and inflates recall. In fact the DOM arm detects 1 of 4 genuinely.
- **Required correction:** State that V-04 is flagged only because the clause fires on every page, and that no skip-link was recognised anywhere. Report "genuine detections" separately, or remove the sentence. Revisit what Table 2's recall of 0.50 means.

**F-07 — High — Section 3.2 (Proposition 1), Introduction, Section 5**
- **Evidence:**
  - "At-most-once per pair" holds for frontier executions. The paper itself says replay re-fires every action on a path, including `click`.
  - So the same (state, action) pair can be executed many times as part of replays. The earlier draft reported 9 replays and 21 replayed steps on this 11-edge app; those numbers are now dropped.
  - The proof says "terminates" and bounds frontier executions at nk, but ignores replay cost.
- **Why it matters:** "At-most-once" reads as a safety guarantee against non-idempotent targets, and the label (and the "SAFE" cell) oversells it. The guarantee does not protect effects, which is the point of the section.
- **Required correction:**
  - Rename the property, for example "once-per-frontier-pair" or "bounded frontier executions", and state in the proposition that replay executions are excluded.
  - Add a replay-cost bound (steps per frontier pair up to depth d) or measure it via F-02.
  - Use "~" or "not provided" for the SAFE cell and keep the existing caveat.

**F-08 — High — Section 3.4 (Proposition 2 and Corollary), abstract, Section 5**
- **Evidence:**
  - The proof is "monotone/antitone". That is true by construction of Eqs. 1–2 and is not a research result.
  - The "relative to the policy vocabulary" caveat makes any mismatch count as under-reporting. Then any observed (FN on forbidden, FP on required) pattern "confirms" the proposition, so the experiment has no way to fail.
  - Over-reporting is covered only by the reversed statement, with no data. "No uniform bias is safe" holds only for a perceiver with a single global bias.
- **Why it matters:** Calling this a "result" and "predicted asymmetry" in the abstract oversells it.
- **Required correction:**
  - Present it as an observation (a lemma), not a contribution headline.
  - State a falsifiable prediction (for example, over-reporting arms produce FP on forbidden and FN on required) and test it. A cheap test is a perturbed perceiver that adds spurious tags, run on the same fixture.
  - Soften the abstract to "consistent with".

**F-09 — Medium — Section 3.2 Definition (exploration graph), Section 4.2, Fig. 2**
- **Evidence:** "Back-edge" is defined as any edge whose target was already discovered. That is a revisit or non-tree edge, and includes cross and forward edges, whereas "back-edge" in graph theory (DFS) means an edge to an ancestor. The claim "6 back-edges regardless of order" is the count of non-tree edges. Edges to the seed are also included. I verified the figure: 11 transitions, 5 tree edges and 6 non-tree edges, matching `app.json`.
- **Why it matters:** Terminology that a graph-literate reviewer will challenge. The code field is `is_back_edge`, so the naming comes from the code.
- **Required correction:** Rename ("revisit edge" or "closing edge"), or define "back-edge" explicitly as non-tree edge and note it is not the DFS notion. Keep the graph cyclic and never prune (immutable).

**F-10 — Medium — Section 3.1 (fingerprint paragraph), Section 4.5 (RQ4), Table 3**
- **Evidence:**
  - "Section 4.5 measures both failure modes on a small scale." In fact it measures stability against noise the normaliser was written to remove, and sensitivity on exactly one deletion.
  - The naive hash is a strawman. Near-duplicate approaches (Yandrapally et al.) and Crawljax-style state abstractions are not compared.
  - Over-merging risks are not tested. For example, `\d{10,}` strips any 10-digit number, including visible phone numbers and IDs, and prefixed tokens are removed everywhere.
  - Table 3 has six identical rows and carries one piece of information. It could be one sentence.
  - The AX-tree noise is two nodes.
- **Why it matters:** The sensitivity claim is weakly supported, and the table adds length without information.
- **Required correction:**
  - Add over-merge tests: mutate visible text, add or remove elements, change a 10-digit visible number, change hidden or aria-hidden content. Report which changes are detected.
  - Collapse Table 3 to a sentence or a two-row table (naive versus φ).
  - Soften the Section 3.1 sentence.

**F-11 — Medium — Section 2.2 (text introducing Table 1), Table 1, Table 1 caption**
- **Evidence:**
  - The text says the cells "still need a final check against the papers before publication" and refers to "an internal novelty analysis of this project". That is a draft status note inside a paper.
  - The StateScout row is self-assessed, with AE ✓ although no live crawl was run in the paper, and NEG, REQ and ROLE ✓.
  - There is no search protocol for how the 14 rows were chosen.
  - The "~" and "?" cells were never spot-checked (README requires this; MEMORY.md says it was not done).
- **Why it matters:** Positioning claims ("No row combines…") rest on an unverified hand-made table.
- **Required correction:**
  - Spot-check each "~" and "?" cell against the cited paper. Resolve or remove the unconfirmed cells.
  - Describe how rows were selected: search terms, venues and date range.
  - Remove the "internal novelty analysis" and "still need a final check" wording.
  - Justify or downgrade the AE ✓ for StateScout, since no live crawl is reported.

**F-12 — Medium — Section 2 related work (Oracles and invariants; Access-control testing)**
- **Evidence:** I confirmed that axe-core's `bypass` rule checks for an internal skip link, heading or landmark (WCAG 2.4.1). That is a deployed web oracle for the paper's own running example R1, and it runs over crawled pages. DAST scanners (for example ZAP passive rules, Invicti) flag debug artifacts left in production. Neither family is cited; MATE covers mobile accessibility only.
- **Why it matters:** The "required-absent" and "forbidden artifact" detections are not unprecedented on the web. The positioning paragraph should engage with them. A systematic search was not possible; I found no direct prior work on role-scoped polarity-typed UI policy, but absence of evidence is not proof.
- **Required correction:** Add and discuss axe-core/WCAG-based checkers and web DAST passive scanners, plus any other web UI static checkers the authors find in a systematic search. Update Table 1. Keep the "no row combines…" claim only if it still holds.

**F-13 — Medium — `references.bib`, printed reference list**
- **Evidence:** Working notes print in the PDF reference list: "Cite the version you read" (liu2024visiondroid), "Listed in the ASE 2019 Demonstrations track on the conference site" (li2019humanoid), and "Preprint, under review at time of retrieval" (dharmaadi2025bacfuzz). The `teoh2026webtestpilot` entry is stale: it is published (DOI 10.1145/3797115, 2026 ACM proceedings) but is cited as a preprint. `liu2025bacscan` lacks pages (CCS '25, pp. 1320–1333). `doupe2012enemy`, `su2017stoat`, `gu2019ape` and similar entries have inconsistent pages or DOIs.
- **Why it matters:** Sloppy and unfinished.
- **Required correction:**
  - Remove all author-facing notes from printed output.
  - Update WebTestPilot to the published version, after the writer verifies the DOI.
  - Choose one arXiv version of VisionDroid and give its correct title and authors.
  - Add the BACScan page range.
  - Make entry formatting consistent.

**F-14 — Medium — Section 3.3 (perception), `apps/agent/perception/gemini.py`**
- **Evidence:** The paper says "Gemini 2.5 Flash". The `gemini.py` docstring says 2.5 Flash, but the actual constant is `_MODEL = "gemini-3.6-flash"`.
- **Why it matters:** A system claim that disagrees with the code. The channel is not evaluated, so the model name is low-stakes, but it is a factual mismatch.
- **Required correction:** Name the model as "a Gemini Flash model (configured identifier in code)" or confirm and cite the identifier actually used. The orchestrator or Track C must resolve the docstring/constant conflict. Do not guess.

**F-15 — Low — Section 2.1, Section 4.1, Fig. 2**
- **Evidence:** The running example numbers the clauses F1, F2, F3, R1 (admin link, delete, debug, skip). The violations are V-01 admin link, V-02 debug, V-03 delete, V-04 skip, so the order differs. Fig. 2 uses V1–V4 without hyphens. The Fig. 1 caption says "Dotted lines indicate which port each node calls", but the figure has no such lines.
- **Why it matters:** Reader confusion and an inaccurate caption.
- **Required correction:** Use one scheme (V-01…V-04 mapped to clauses) in text, table and figures. Fix the Fig. 1 caption or draw the lines.

**F-16 — Low — Section 3.3, Section 6, Section 3 intro**
- **Evidence:** Project-internal language: "modules owned by four sub-teams", "a decision for the perception track", "internal novelty analysis". Also unevaluated system components are described (FastAPI service, VS Code extension, rate-limited provider).
- **Why it matters:** Internal organisational detail does not belong in a paper.
- **Required correction:** Replace with neutral wording ("a pending design decision"). Describe only components the paper relies on.

**F-17 — Low — Throughout (Sections 4.5, 5, 6, 7), abstract**
- **Evidence:** The "fakes and static HTML, one application" caveat appears 4–5 times with near-identical wording. Some sentences are formulaic ("Two consequences deserve to be stated plainly", "The pattern is the one X predicts").
- **Why it matters:** Padding that lengthens the paper. The paper is 19 pages (14 body plus 5 of references) against an unspecified venue limit.
- **Required correction:** State limitations once in Threats to Validity and refer back to it. Trim to the venue limit once it is known.

**F-18 — Low — Section 4.1, Artifact paragraph, reproducibility**
- **Evidence:** No software, hardware or package versions are recorded. The artifact is a repo path, not an archived release. The text says "fixed seeds (RQ2–RQ4)", but only RQ4 uses a seed; the other experiments are deterministic.
- **Why it matters:** Reproducibility and a small factual error.
- **Required correction:** Record the Python, uv and LangGraph/Playwright versions and the commit hash. Say "RQ4 uses seed 7". Plan an archive (Zenodo or similar) with the author's agreement.

## 4. Integrity assessment

**Plagiarism evidence**
- No similarity report or corpus was available, so comprehensive plagiarism verification has not been performed. This is not a plagiarism-free verdict.
- **Internal comparison (verified, mechanical):** I compared 8-word shingles of the Springer text against the earlier `docs/report/paper/` and `ieee/` drafts. Overlap is 3–18% by section: related 0.15, model 0.18, conclusion 0.17, evaluation 0.12, system 0.11, discussion 0.09, introduction 0.06. A 7-word shingle comparison against `novelty-analysis.md` found 21 shared shingles in related work (of 1160), 3 in system, and none elsewhere. That is the same team re-explaining its own material. It is not external plagiarism, but self-reuse across drafts should be disclosed if any draft is ever submitted or published elsewhere.
- **External spot checks (limited):** Three distinctive sentences from the introduction and related-work sections were run through web search. There were no matches. Nothing in the text appears to be lifted from the cited papers, but I read only abstracts and did not compare full texts against the cited papers. Low confidence in either direction.
- **Unverified suspicion, not flagged:** None observed. The Table 1 cell contents derive from the project's own matrix.

**Citation integrity**
- **Verified by web search (8 of 40):**
  - `barr2015oracle`: IEEE TSE 41(5) 507–525, 2015, confirmed. It is no longer unverified.
  - `liu2025bacscan`: CCS 2025, confirmed (pp. 1320–1333).
  - `alhamoud2025negation`: CVPR 2025, confirmed.
  - `levy2026stwebagentbench`: ICLR 2026, confirmed.
  - `teoh2026webtestpilot`: real, published at ACM (DOI 10.1145/3797115); the bib says preprint (F-13).
  - `li2019humanoid`: ASE 2019 (demonstrations), confirmed.
  - `xiong2024kea`: ASE 2024, confirmed.
  - `mesbah2012invariant`: IEEE TSE 38(1) 35–53, confirmed.
- **Not independently verified (32):** these rely on the 2026-09-22 novelty-agent check. I did not find fabrication in the sample.
- **Claim-support concerns:**
  - Negation citations (`alhamoud2025negation`, `yuksekgonul2023aro`, `ma2023crepe`) concern natural images and CLIP retrieval. The paper acknowledges this, but Section 3.4's "therefore a polarity-dependent risk profile" for UI yes/no queries is an extrapolation (F-04).
  - All 40 entries are cited, per MEMORY.md and the compile (no undefined references).
  - No single-source dependence is evident.

**AI-style risk: Low to Medium (Indeterminate beyond that)**
- **Evidence:**
  - The prose is fluent and uniform, with some formulaic phrasing.
  - Limitations are repeated across sections.
  - Specific, checkable details are plentiful (file names, counts, edge cases), and the claims are generally honest about what is not done. That counts against a generic-text pattern.
  - Technically, the paper's conflicts (F-04, F-06, F-08) come from over-interpretation, not fabricated detail. I found no fabricated results or references.
- **Limitations:** Style cannot establish authorship. The writer is a documented drafting agent, so AI assistance is expected here, and disclosure policy depends on the venue.

**External detector results:** None were provided, and none are reported or invented.

**Verification limitations**
- No full-text comparison against the cited works.
- Only 8 of 40 references independently checked.
- The live Playwright, VLM and Neo4j/Redis pipeline was not run.
- The tests (`pytest`) were not run; `uv run` was used only to replay the experiment functions in-process.
- Prior-art completeness cannot be established by search. F-12 is a gap I found, and others may exist.

## 5. Revision plan, ranked

**Factual corrections (do first)**
1. F-06: V-04 is a vacuous true positive.
2. F-04: remove "VLM never decides existence/absence" and "cannot be hallucinated".
3. F-14: Gemini model naming.
4. F-18: seed attribution. F-15: caption and labels.
5. F-07: rename "at-most-once" and add the replay-excluded qualifier.
6. F-11 and F-16: remove draft-status and internal-organisation text.

**New experiments (code-level; the writer has Bash and may extend `run_experiments.py`, writing results only under `docs/report/data/`)**
1. F-01: real `negation.audit` on oracle-perceived maps.
2. F-02: loop counters plus resume (orchestrator authorisation required for demo_crawl numbers).
3. F-08: an over-reporting arm to test the opposite polarity pattern.
4. F-10: over-merge sensitivity tests.
5. F-03: mutants of `broken-admin`, plus a hand-written invariant baseline.
- More subjects and an end-to-end Playwright run are blocked (section 9).

**Source verification**
1. F-11: spot-check every "~" and "?" cell. F-12: search for and add web a11y/DAST prior art.
2. F-13: update WebTestPilot, BACScan pages and the VisionDroid version.
3. Verify the remaining 32 references (or mark them unverified).

**Structural revisions**
1. F-05: recast RQ2 and the abstract.
2. F-08: demote Proposition 2 to an observation and soften the abstract.
3. F-09: rename "back-edge".
4. F-10: collapse Table 3.
5. F-17: dedupe limitations; trim to the venue limit.

**Stylistic**
- Remove formulaic hedges and fix the Fig. 1 caption.

## 6. Score audit trail

This is the first audit; there is no previous score. Baseline: 5.7/10 (breakdown in section 2).

## 7. Anti-gaming notes for the writer

- Do not raise the score by lengthening, by adding more tables, or by hedging more.
- Score gains come from evidence (F-01, F-02, F-03), from removing contradictions (F-04, F-06, F-08) and from verified sources (F-11, F-12, F-13).
- Do not claim the paper is plagiarism-free, and do not report detector numbers.

## 8. Writer handoff (machine-readable)

```json
{
  "audit_iteration": 1,
  "iteration_limit": 4,
  "remaining_iterations_after_this": 3,
  "quality_threshold": 8.0,
  "target_venue": "Springer svproc proceedings (software engineering / AI agents); no named venue; page limit unknown",
  "paper_source": {
    "immutable_reference": "docs/report/springer/main.tex + sections/{introduction,related,model,system,evaluation,discussion,conclusion}.tex + references.bib (state at audit time, 19 pages compiled)",
    "write_scope": "docs/report/springer/ and docs/report/data/ + docs/report/experiments/ only if new experiments are authorised"
  },
  "required_format": {
    "class": "svproc (unmodified svproc.cls); Paper.tex is the exemplar",
    "mainmatter": true,
    "abstract_words": "70-150 (currently 142)",
    "bib": "plain + natbib numeric",
    "packages_allowed": "url helvet courier graphicx multirow booktabs amsmath amssymb natbib tikz",
    "forbidden": "amsthm; modifying svproc.cls",
    "captions": "tables above, figures below"
  },
  "current_score": {
    "overall": 5.7,
    "breakdown": {
      "novelty_originality": {"score": 0.9, "max": 2.0},
      "technical_correctness": {"score": 1.1, "max": 2.0},
      "evidence_results": {"score": 0.8, "max": 2.0},
      "literature_citations": {"score": 1.1, "max": 1.5},
      "structure_coherence": {"score": 0.7, "max": 1.0},
      "reproducibility_limitations": {"score": 0.7, "max": 1.0},
      "writing_presentation": {"score": 0.4, "max": 0.5}
    },
    "recommendation": "Major Revision",
    "readiness": "Not Ready"
  },
  "findings": [
    {"id": "F-01", "severity": "Critical", "location": "evaluation.tex Artifacts para + RQ1; Table 2 row 1; abstract",
     "evidence": "oracle arm = FakePerception.analyze + fake.audit (not negation.audit.audit); fake reads data-tag, the encoding the ground truth uses",
     "correction": "Add arm: real negation.audit on fake-perceived maps; relabel the old arm; rewrite RQ1 and abstract to say exactly what each arm exercises", "status": "open", "needs_new_run": true},
    {"id": "F-02", "severity": "Critical", "location": "introduction.tex contribution 3; model.tex Prop 1; evaluation.tex RQ1; Fig 2",
     "evidence": "No loop-level measurement in paper; Fig 2 is derived by inspection; crash/resume claim untested in paper; docs/demo_crawl.py exists",
     "correction": "Add E5 to run_experiments.py (pairs, duplicates, replays, replayed steps, back-edges, termination, skipped with a fill/submit injected, resume test) OR demote contribution 3 and drop the 'keeps the graph cyclic' clause from RQ1", "status": "open", "needs_orchestrator_authorisation": true},
    {"id": "F-03", "severity": "Critical", "location": "evaluation.tex whole; discussion.tex; conclusion.tex",
     "evidence": "n=1 app, 4 positives, authors wrote app and tool, no baseline, no variance",
     "correction": "Add mutants of broken-admin, >=2 further subjects, and a Crawljax/ATUSA-style hand-written invariant baseline; otherwise cut claims to fixture-level", "status": "blocked_in_part", "blocked_by": "additional subjects and baseline need author/orchestrator decision and possibly new apps"},
    {"id": "F-04", "severity": "Critical", "location": "introduction.tex contribution 2; related.tex LLM/VLM para; system.tex Perception",
     "evidence": "Text: VLM 'never decides existence or absence'/'cannot be hallucinated'. System: VLM adds tags and capabilities; policy subjects are tags/capabilities; gemini.py::_gemini_capabilities adds extra_capabilities",
     "correction": "Restate: VLM cannot add/remove DOM/AX elements but can add tags/capabilities, so grounding errors persist and fall under Prop 2; remove the absolute claims; mark unevaluated consistently", "status": "open"},
    {"id": "F-05", "severity": "High", "location": "abstract; evaluation.tex RQ2; discussion.tex; conclusion.tex",
     "evidence": "P=0.29 / R=0.50 arises from policy.json subjects (admin-link, debug-panel, skip-to-content) vs tagger output (admin, debug); ablation E4 removes FP; E4 designed post hoc on same 4 items",
     "correction": "Recast RQ2 as a vocabulary-mismatch case study; label E4 exploratory; remove numeric P/R from abstract or qualify", "status": "open"},
    {"id": "F-06", "severity": "High", "location": "evaluation.tex RQ2 'finds two (V-03 and V-04)'; Table 2",
     "evidence": "experiments.json: skip-link required_absent fires on all 6 pages in the DOM arm (5 FP + the admin TP); no skip link recognised anywhere, so the V-04 hit is coincidental",
     "correction": "State that V-04 is flagged only because the clause fires everywhere; report genuine detections separately (V-03 only in DOM arm)", "status": "open"},
    {"id": "F-07", "severity": "High", "location": "model.tex Prop 1 and following paragraph; Table 1 SAFE cell",
     "evidence": "frontier-pair at-most-once only; replay re-fires prefix actions incl. click (state.py:48 REPLAY_SAFE_KINDS={navigate,click,back}); proof ignores replay cost",
     "correction": "Rename property, scope the proposition to frontier executions, add replay-cost bound or measurement, keep 'click is replay-safe' statement exactly", "status": "open"},
    {"id": "F-08", "severity": "High", "location": "model.tex Prop 2 + Corollary; abstract; discussion.tex",
     "evidence": "Proof is monotone/antitone by construction; 'relative to vocabulary' caveat makes the proposition unfalsifiable on RQ2; no over-reporting data",
     "correction": "Present as observation; state a falsifiable prediction and test an over-reporting (spurious-tag) arm; soften abstract to 'consistent with'", "status": "open", "needs_new_run": true},
    {"id": "F-09", "severity": "Medium", "location": "model.tex Def (exploration graph); evaluation.tex RQ1; Fig 2",
     "evidence": "'back-edge' defined as any edge to an already-discovered node (non-tree edge); not the DFS notion",
     "correction": "Rename (revisit/closing edge) or define explicitly; keep graph CYCLIC and never prune", "status": "open"},
    {"id": "F-10", "severity": "Medium", "location": "model.tex fingerprint paragraph; evaluation.tex RQ4; Table 3",
     "evidence": "noise = exactly what normaliser strips; sensitivity = one deletion; no over-merge tests (e.g. \\d{10,} strips visible numbers); Table 3 = 6 identical rows",
     "correction": "Add over-merge/sensitivity tests; collapse Table 3; soften 'measures both failure modes'", "status": "open", "needs_new_run": true},
    {"id": "F-11", "severity": "Medium", "location": "related.tex Table 1 + intro paragraph + caption",
     "evidence": "Text says cells 'still need a final check ... before publication' and cites 'internal novelty analysis'; ~/? cells never spot-checked; StateScout row self-assessed (AE tick without live crawl); no search protocol",
     "correction": "Spot-check each ~/? cell vs paper; describe row selection; remove draft-status wording; justify AE", "status": "open"},
    {"id": "F-12", "severity": "Medium", "location": "related.tex Oracles and invariants",
     "evidence": "axe-core 'bypass' rule (WCAG 2.4.1) checks skip links on web pages; DAST passive scanners flag debug artifacts; none cited",
     "correction": "Add and discuss web a11y checkers and DAST passive rules (plus systematic search for others); update Table 1; keep 'no row combines' only if it still holds", "status": "open"},
    {"id": "F-13", "severity": "Medium", "location": "references.bib (printed list)",
     "evidence": "Printed notes 'Cite the version you read', 'Listed in the ASE 2019 Demonstrations track...', 'Preprint, under review...'; teoh2026webtestpilot now published (DOI 10.1145/3797115); liu2025bacscan lacks pages 1320-1333",
     "correction": "Strip working notes from printed output; update/verify WebTestPilot; add BACScan pages; settle VisionDroid version", "status": "open"},
    {"id": "F-14", "severity": "Medium", "location": "system.tex Perception",
     "evidence": "Paper: Gemini 2.5 Flash. gemini.py docstring says 2.5 but _MODEL='gemini-3.6-flash'",
     "correction": "Neutral wording or confirmed identifier; escalate docstring/constant mismatch to Track C; do not guess", "status": "open"},
    {"id": "F-15", "severity": "Low", "location": "related.tex Sect 2.1; evaluation.tex Sect 4.1; Fig 1 and Fig 2",
     "evidence": "F1/F2/F3 order differs from V-01..V-04; Fig 2 uses V1-V4; Fig 1 caption mentions dotted lines not drawn",
     "correction": "Unify labels; fix caption", "status": "open"},
    {"id": "F-16", "severity": "Low", "location": "system.tex intro; discussion.tex; related.tex",
     "evidence": "'four sub-teams', 'perception track', 'internal novelty analysis'; FastAPI/VS Code extension mentioned though unevaluated",
     "correction": "Neutral wording; keep only relied-on components", "status": "open"},
    {"id": "F-17", "severity": "Low", "location": "evaluation.tex 4.5, discussion.tex, conclusion.tex",
     "evidence": "Same limitation repeated 4-5 times; formulaic hedging; 19 pages vs unspecified limit",
     "correction": "State once in Threats; trim to venue limit when known", "status": "open"},
    {"id": "F-18", "severity": "Low", "location": "evaluation.tex Artifacts paragraph",
     "evidence": "No environment/versions/commit; 'fixed seeds (RQ2-RQ4)' but only RQ4 (E2, seed 7) is seeded; artifact is a repo path",
     "correction": "Record versions + commit hash; correct seed statement; plan archived artifact", "status": "open"}
  ],
  "verified_ok_do_not_regress": [
    "All table values equal docs/report/data/experiments.json; re-run of e1_e3()/e2() reproduced the stored JSON exactly",
    "Fig 2 edge counts: 11 transitions, 5 tree edges, 6 non-tree edges, matching test-apps/broken-admin/app.json",
    "Compiles with pdflatex+bibtex (scratch copy): 19 pages, only an OT1 bx/sc font substitution warning; abstract 142 words"
  ],
  "must_not_change": [
    "The exploration graph is CYCLIC; never call it a DAG; never prune back-edges; loop prevention = visited (state_id, action_id) set only",
    "RQ1/RQ3 use FakePerception and a scripted crawler; never present as end-to-end",
    "REPLAY_SAFE_KINDS = {navigate, click, back}; click is replay-safe; keep the residual-risk statement precise; never write 'only navigation is replayed'",
    "Only report numbers present in data/experiments.json or reproducible by run_experiments.py (and any new E-arms the writer actually runs and stores)",
    "Do not invent citations, results, datasets, or detector scores; do not claim plagiarism-free",
    "Authors remain placeholders; do not modify svproc.cls; do not load amsthm",
    "Keep the honest 'we formalise and combine' scoping; do not claim first crawler, novel cyclic graph, novel fingerprint, OWASP A01 detection, NL-policy-driven audit, or solved VLM negation",
    "Keep the existing disclosures of what each experiment arm uses (fake algebra, ax_tree=None, no browser, in-process patch)"
  ],
  "blocked_by_missing_evidence": [
    {"item": "End-to-end Playwright -> build_semantic_map -> negation.audit result", "needed": "Policy-subject vs tagger vocabulary decision (Track C) and a live-browser run"},
    {"item": "VLM / hybrid presence-absence accuracy per polarity (probe set)", "needed": "Gemini key, wired channel, labelled probe set"},
    {"item": "Additional subject apps and a Crawljax+ATUSA baseline (F-03)", "needed": "Authors to supply or approve apps/baseline; cannot be fixed by rewriting"},
    {"item": "demo_crawl.py loop counters (F-02)", "needed": "Orchestrator authorisation to re-run and store results under docs/report/data/"},
    {"item": "Author names, affiliation, venue, page limit", "needed": "Author decision"},
    {"item": "Resolution of Gemini model identifier mismatch (F-14)", "needed": "Track C"},
    {"item": "Plagiarism check", "needed": "Similarity report / corpus; none available"},
    {"item": "AI-detector results", "needed": "External detector; none provided"}
  ],
  "unresolved_questions": [
    "Does the venue impose a page limit below 19 pages?",
    "Should the policy vocabulary be renamed, or should perception read data-tag, for the fixed-vocabulary experiment?",
    "Will the authors accept adding mutants / second subject apps within the iteration budget?",
    "Remaining 32 references are only checked by the 2026-09-22 novelty agent, not by me"
  ],
  "previous_iterations": [],
  "iteration_budget": {"threshold": 8.0, "iterations_remaining_after_this": 3, "note": "Reaching 8.0 requires F-01, F-02 and F-03 evidence, not prose-only revision; if blocked, mark blocked and report honestly rather than rewriting prose"}
}
```

## 9. Orchestrator notes

- I am a subagent and did not invoke the writer. I created no files in the repo. Scratch artifacts (the scratch compile copy and page PNGs) are in the session scratchpad only.
- I did not run `pytest`, `make` in place, or the live pipeline. In-process, I only replayed the two experiment functions. `git status` is unchanged apart from the pre-existing entries.
- **Decisions needed from you before iteration 2** (they determine whether 8.0 is reachable):
  - (a) Authorise running `docs/demo_crawl.py` and adding the loop counters and resume test as stored results (F-02).
  - (b) Authorise adding an arm that feeds fake-perceived maps to the real `negation.audit` (F-01), plus an over-reporting arm (F-08) and over-merge fingerprint tests (F-10).
  - (c) Decide whether further subject apps and a Crawljax/ATUSA-style baseline can be provided (F-03). Without them, expect a score ceiling near 6.5–7.0 even with all prose fixed.
  - (d) Resolve the Track C vocabulary and Gemini model-id questions (F-05, F-14).

Relevant files:
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/main.tex`
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/sections/` (`introduction`, `related`, `model`, `system`, `evaluation`, `discussion`, `conclusion`)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/references.bib`
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/data/experiments.json`
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/experiments/run_experiments.py`
- `/home/kr95/Projects/final-year-project/statescout-ai/apps/agent/perception/gemini.py`
- `/home/kr95/Projects/final-year-project/statescout-ai/apps/agent/orchestrator/state.py`
- `/home/kr95/Projects/final-year-project/statescout-ai/apps/agent/orchestrator/explore.py`
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/demo_crawl.py`

Sources checked:
- [Barr et al., Oracle Problem survey](https://discovery.ucl.ac.uk/1471263/)
- [BACScan, CCS 2025](https://secsys.fudan.edu.cn/publications/content/2025-12-10-003)
- [Alhamoud et al., CVPR 2025](https://openaccess.thecvf.com/content/CVPR2025/html/Alhamoud_Vision-Language_Models_Do_Not_Understand_Negation_CVPR_2025_paper.html)
- [ST-WebAgentBench, ICLR 2026](https://iclr.cc/virtual/2026/poster/10009904)
- [WebTestPilot](https://arxiv.org/abs/2602.11724)
- [Kea, ASE 2024](https://conf.researchr.org/details/ase-2024/ase-2024-research/5/General-and-Practical-Property-based-Testing-for-Android-Apps)
- [Humanoid, ASE 2019 demonstrations](https://www.se.cs.uni-saarland.de/conferences/ASE/ase2019/details/ase-2019-Demonstrations/23/Humanoid-A-Deep-Learning-based-Approach-to-Automated-Black-box-Android-App-Testing.html)
- [ATUSA invariant-based testing, TSE](https://people.ece.ubc.ca/amesbah/resources/papers/tse11.pdf)
- [axe-core bypass rule](https://dequeuniversity.com/rules/axe/4.10/bypass)