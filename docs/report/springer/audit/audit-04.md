# Audit report: StateScout Springer paper (iteration 4 of 4, FINAL)

I wrote no repo files. The scratch work was a compile copy, a rerun script, shingle scripts and fetches, all in the session scratchpad. I loaded `run_experiments.py` as a module and called the `e*()` functions in-process. I never called `main()` and wrote nothing to `data/`.

`git status` at the repo root shows only the pre-existing entries: the staged `.claude/hooks/track_b_paths.py`, the untracked `.claude/agents/*` and `docs/report/`. `git status` on `apps/`, `tests/`, `test-apps/`, `services/` and `infra/` is empty. I found no new `.pyc` files newer than revision-matrix-04.

## 1. Executive verdict

- **Overall score: 7.8 / 10** (audit 3: 7.5; audit 2: 6.9; audit 1: 5.7). The 8.0 threshold is not met.
- **Recommendation: Major Revision, close to Minor.** A fixture-level workshop paper is within reach. The remaining gap is evidence breadth and independence, which prose cannot fix.
- **Publication readiness: Borderline.**

**Three most serious problems**
1. **No independent subject and no browser, VLM or hybrid result (F-03, blocked).** Every subject is same-project. The three new apps are tiny, single-defect and chosen by the authors. The headline evidence for the system as an auditor of real UIs is still absent.
2. **"Pre-registered" is an unverifiable authorial statement (F-33, new, Medium).** The paper uses it in a table caption and in the text. Nothing in the repo or JSON can establish ordering, and the paper does not say so.
3. **A8's E12 result is in-sample (F-34, new, Medium to Low).** A8's XPaths were written after reading the same HTML they are scored on. The ground truth was set narrower than what the HTML and the README's own policy sentence show. The consent control is circular for A8. The disclosures are present, but the "A8 finds all three" headline and the abstract's "beats it" are not fully qualified.

**Checks that passed**
- Re-running every experiment function reproduces the stored JSON exactly, including E11, E12 and E13, under four hash seeds.
- Compiled in a scratch copy: 20 pages, 0 overfull boxes, 0 undefined references, 0 BibTeX warnings, abstract 146 words.
- `svproc.cls` is byte-identical to the one in the template zip, and `amsthm` is not loaded.
- There is no dangling reference to the removed figure.

## 2. Verification of the writer's claims

| Claim | Result |
|---|---|
| F-27 resolved | **Agree on execution, with caveats.** The three apps are evaluated, stored in E12 and disclosed as same-project and tiny. Independence is not achieved, and the "pre-registered" wording is not verifiable (F-33, F-34). |
| F-28 resolved | **Agree on accuracy, with a URL caveat (F-35).** See section 3. |
| F-29 resolved in the paper | **Agree for the paper.** The wording is now "element types, link targets, visible text". The stored artifact still carries old wording (F-36). |
| F-30 resolved | **Agree.** The plain A3 vs A8 sentence is present. A2s is presented as an oracle perceiver without annotations. Renames are reported per variant: 3 independent, and the combined row is flagged as double-counting. |
| F-31 resolved | **Agree.** E11 reproduces under hash seeds 0, 1, 3 and 12345. The BibTeX warning is gone. The docstring E-order is fixed. MEMORY.md sections 3 to 8 were rewritten, but the file is still not fully consistent (F-36). Committing the artifact remains an author decision. |
| F-25-residual resolved | **Agree.** The Noseevich pages are removed and the intro sentence is hedged to "seldom". It is still uncited (Low). |
| F-32 partial | **Agree.** MATE stays "?". I confirmed the MATE bib entry itself (below). AXNav REQ "~" with a caption note is fair. |
| F-03 partial | **Agree.** See F-34. |
| F-14 blocked | **Agree.** `system.tex` says "a Gemini Flash model". Track C must reconcile the identifier. |
| F-18/F-24 partial | **Agree.** The key map is extended, but the artifact is uncommitted and unarchived, and the paper says so. |
| F-17 | **Agree for restatements.** The page limit is unknown. 20 pages hold after the figure removal. |
| E1_E3, E2, E5-E10, meta identical to stored v3 | **Verified** against my saved audit-3 snapshot. The only differences are E11 row 0 `second_run_attempts_of_claimed_pairs` (1 became 0) and the `key_map` RQ5 entry. |

### (1) Can "pre-registration" be verified?

**No.** The evidence available is:
- The derivation is stored in the JSON, but only as an output of the script that also contains the XPaths and the results.
- The ordering claim appears only in script comments ("BEFORE any HTML was opened", "written after reading the HTML, before any arm was run; not edited afterwards") and in the JSON `disclosure` string.
- `docs/report/` is untracked, so there is no git history. The script and JSON mtimes are six seconds apart (09:59:21 and 09:59:27), so file times say nothing about derivation order.
- There is no hash, no timestamped registry entry and no commit.
- The README of `broken-feature-flag-demo` quotes the button's HTML literally.
- Audit 3, which the writer had, described HTML-level details: the "Admin Dashboard (Violation)" link label and the Export Data button.
- The derivation uses page names (`index.html`, `dashboard.html`) and "one page", which come from a directory listing, not the README.

So "before any HTML was opened" is, at best, a statement about the writer's own file reads.

**Is the paper honest about this?** Only partly. For A8 on the fixture the paper writes "which we state but cannot evidence". The E12 paragraph states ordering as fact and uses the word "pre-registered" in the Table 9 caption and in "a false positive under the pre-registered truth". The term implies an externally anchored registration. The honest wording is "derived from the README text first; ordering is an authorial statement the artifact cannot evidence". This is F-33.

### (2) Was A8 fitted to the HTML it is scored on?

**Yes, for E12.** The evidence is:
- The paper discloses that the invariants were "written after reading the HTML".
- The invariants are the exact selectors of the known defect. For example, `.//a[@href='admin.html']` and `.//button[.='Export Data']` match elements that exist only on the defective page.
- A8's 3/3 with 0 FP is therefore expected by construction. It is in-sample and not evidence of generalisation.
- A3 got only README-derived subject strings. A8 got visibility of the HTML. This asymmetry is not named as a caveat on the A3 vs A8 comparison. The post hoc A3 variant corrects it in the other direction, because that respelling was chosen after seeing the tagger's output.
- The truth is narrower than what the HTML shows. The feature-flag README's own quoted policy says the user must not see the "Export Data button or Advanced Analytics panel". The page's heading reads "Advanced Analytics (Premium Feature Leak)". The writer treated the panel as "README-ambiguous" and left it out of the truth.
- A8's exact-heading query (`h2[.='Advanced Analytics']`) misses it. Under a natural reading that is a false negative.
- The RBAC dashboard's own banner calls the "Delete All Records" button a violation. A8 misses that too.
- The paper does disclose both misses ("A8's shortfalls lie outside that truth"). Even so, its headline "A8 finds all three defects with no false positive" is favourable.

**Does the comparison avoid overclaiming?** The body mostly does. The abstract's "a label-based script beats it" rests on the fixture and on in-sample E12 results. The paper never says plainly that the E12 A8 numbers are in-sample.

### (3) Is the vacuous-hit control sound?

- **For A3: yes.** The control inserts `<div id="cookie-banner" role="dialog">…<button>Accept</button></div>` in memory. A3 still reports the missing-consent violation. That shows the clause fires regardless of the page, because the tagger has no consent vocabulary. The check is simple and correct.
- **For A8: circular.** The JSON note admits that A8's queries include the inserted markup by construction. The paper does not report this. A8's 1/0 on consent appears in Table 9 with no caveat, although any absence-based clause scores 1/1 on a page with no banner.
- **Net effect:** the consent row discriminates nothing for either arm. Only two of the three E12 rows carry information.
- The control tests only one inserted banner shape, which was authored alongside the selectors.

### (4) Re-run, in-process, into scratch only

I called `e1_e3, e2, e5, e6, e7, e8, e9, e10, e11, e12, e13`, `_meta()` and `KEY_MAP` and compared each result against the stored JSON. I used `PYTHONHASHSEED` 0, 1, 3 and 12345, with `PYTHONDONTWRITEBYTECODE` set.

- **All 13 keys matched under every seed.** That includes E11, whose hash-seed field is now seed-independent, and `meta`, whose git head is the same.
- Against my saved audit-3 snapshot: E1_E3, E2, E5-E10 and `meta` are identical. E11 differs in one field and `key_map` gained entries.

### (5) Compile in a scratch copy

- **Pages:** 20.
- **Overfull boxes:** 0.
- **Underfull boxes:** several, none visible-severity.
- **Undefined references:** none.
- **BibTeX warnings:** 0.
- **Font warning:** one OT1 small-caps warning.
- **Abstract:** 146 words.
- **Class file and packages:** `svproc.cls` is byte-identical to the template zip, and `amsthm` is not used.
- **Figure removal:** `grep` finds no "Fig." or "figure" in the sections.

### (7) New slips, working-note text, overclaims

- No dangling figure reference. No working-note, track or audit text leaks into the sections.
- `system.tex` still opens with "four nodes (scan, reason, act, observe)" and then lists the same four nodes again. This is a leftover of the removed figure (Low, F-37).
- The abstract, intro and conclusion are scoped to fixture level, and I found no overclaim there. The abstract says "a label-based script beats it" without saying that the comparison is in-sample on both the fixture and E12 (F-34).
- The intro's "a test suite seldom contains a scenario for a button that should not exist" is hedged but uncited, and negative assertions are common in test tools (Low).
- The stored artifact is out of step with the paper (F-36):
  - E10's JSON note still says "reading roles and visible text … written once and not tuned".
  - The `XPATH_INVARIANTS` comment in the script says "Invariants over roles and visible text … not tuned afterwards".
  - MEMORY.md still says "Proposition 2" in sections 2 and 3 and "49 entries". I did not recount the bib.

## 3. LangGraph durable-execution citation: is the claim accurate, and is the entry?

**The claim is accurate. The entry has a stale URL.**

- A direct fetch of the cited URL, `docs.langchain.com/oss/python/langgraph/durable-execution`, today redirects to the **Persistence** page. That page does not contain the two statements. The writer's caveat that direct fetches returned other sections was correct, and so is the bib note that the statements came from search excerpts.
- The Wayback Machine has snapshots of the original page (for example the 2025-12-13 and 2026-03-15 captures). I read the 2025-12-13 capture. It says that when a workflow resumes it does not resume from the same line of code but replays from an appropriate starting point. It also says: "If you're using a StateGraph (Graph API), the starting point is the beginning of the node where execution stopped." It advises idempotent side effects and wrapping side effects or non-deterministic operations in tasks or nodes. The paper's sentence, "a resumed node restarts from its beginning and side effects should be idempotent or wrapped in tasks", matches this snapshot.
- Current live docs carry the same behaviour elsewhere. The `interrupts` page says the node restarts from the beginning when resumed, and that side effects before `interrupt` should be idempotent. The `functional-api` page says a started-but-unfinished task may run again on resume, so side effects should be idempotent.
- **Required fix (F-35, Low):** add the archived URL, or the `interrupts` and `functional-api` pages, to the entry, and keep the "read as of" note. The E5 numbers themselves are measured and unaffected.

## 4. Reference verification (extended this round)

- **MATE (`eler2018mate`):** The Crossref lookup by title returned DOI `10.1109/icst.2018.00021`, title "Automated Accessibility Testing of Mobile Apps", ICST 2018, pages 116–126, authors Eler, Rojas, Ge, Fraser. The bib entry is correct. My first DOI guess was wrong, so I looked it up by title instead.
- **MATE contents:** The IEEE page and Semantic Scholar would not serve an abstract (Semantic Scholar was rate-limited). The search snippet says only that MATE "applies different checks for accessibility issues related to visual impairment". That does not name the checks, so the Table 1 "?" for NEG and REQ is honest and stays.
- **Still unverified:** Memon 2003 pages, the venue years for WebArena and OSWorld, and the full texts of cited works other than ATUSA (checked in audit 2). About 43 of 47 entries have now been checked at some level, with no fabrication or misattribution found. I did not recount the current bib total (MEMORY.md says 49).
- **Still open:** the four unrelated "college references" were deliberately not added. I did not penalise their absence.

## 5. Detailed scoring and audit trail vs 7.5

| Criterion | Score | Max | Change | Justification |
|---|---:|---:|---:|---|
| Novelty and originality | 1.0 | 2.0 | 0 | Still a thin formulation: a typed polarity field, a role scope and a vocabulary. Positioning is accurate. |
| Technical correctness and methodology | 1.7 | 2.0 | +0.05 | F-29 and F-31 are fixed and the E11 seed dependence is gone. The E5 mechanism is now tied to documented LangGraph behaviour. Deductions: the unverifiable "pre-registered" wording, A8's in-sample E12 scoring, a truth narrower than the README policy sentence, and a circular A8 control. |
| Evidence, experiments, results | 1.55 | 2.0 | +0.15 | E12 adds three real unannotated subjects and E13 adds per-variant renames. The vacuous-hit control is sound for A3. Capped by same-project authorship, tiny single-defect apps, one non-informative row, no independent subject and no browser, VLM or hybrid result. |
| Literature and citation quality | 1.35 | 1.5 | +0.05 | The LangGraph claim is accurate against a Wayback snapshot, the MATE bib entry is verified and the Noseevich pages are resolved. Left open: the stale LangGraph URL, MATE contents, and Memon pages. |
| Structure, reasoning, coherence | 0.9 | 1.0 | 0 | Clean, and the figure removal introduced no dangling references. A duplicated node list remains. The page limit is unknown. |
| Reproducibility and limitations | 0.9 | 1.0 | +0.05 | The full rerun is exact under four hash seeds, and the artifact limits are stated. The artifact is still uncommitted and unarchived, and its text is stale. |
| Academic writing and presentation | 0.4 | 0.5 | 0 | Fluent and precise. |
| **Total** | **7.8** | **10.0** | **+0.3** | |

**Audit trail**
- Technical +0.05: F-29, F-31 and the E5 documentation link are verified. The offset is the new F-33 and F-34.
- Evidence +0.15: E12 and E13 are real, reproducible and mostly honestly framed. The raise is held back because the results are in-sample or non-discriminating.
- Literature +0.05: F-25 residual is resolved and the LangGraph claim checks out. The stale URL and the open MATE cell remain.
- Reproducibility +0.05: the seed fix and the rerun are verified. The uncommitted artifact keeps this below the maximum.
- Novelty, structure and writing: no change.
- No score rose because of length. The paper stayed at 20 pages.

## 6. Critical findings

**Earlier findings: status as verified**
- **Resolved:** F-01, F-02 (at fake level), F-04 to F-10, F-12, F-13, F-15, F-16, F-17 (restatements), F-19, F-20, F-22, F-23, F-25 (including the residual page range), F-26, F-27, F-28, F-29 (paper), F-30, F-31.
- **Partial:** F-03, F-11/F-21 and F-32 (MATE), F-18/F-24.
- **Blocked:** F-14.

**New findings**

- **F-33, Medium. `evaluation.tex`, "Three further apps" paragraph and Table 9 caption.**
  - Evidence: "pre-registered" is used for a claim that the repo and JSON cannot evidence (section 2, point 1).
  - Why it matters: it presents an authorial statement as externally anchored.
  - Correction: replace it with "derived from the README text first (ordering an authorial statement the artifact cannot evidence)" and drop "pre-registered" from the caption and the JSON and script keys. If the authors want a genuine pre-registration for any future work, commit the derivation before the HTML-informed step.

- **F-34, Medium to Low. `evaluation.tex`, same paragraph; abstract.**
  - Evidence: A8's E12 XPaths are in-sample; the truth excludes the README-named Advanced Analytics panel and the RBAC delete button; the consent control is circular for A8 and Table 9 does not say so; the abstract's "beats it" is unqualified on this point (section 2, points 2 and 3).
  - Correction:
    - State that A8's E12 results are in-sample and non-informative as a measure of generalisation.
    - Report the truth variant that includes the policy-named analytics panel, or state that A8 would then miss one of the clauses.
    - Mark the A8 consent row as non-discriminating in Table 9.
    - Add "in-sample" or "on these pages" to the abstract's "beats it" clause.

- **F-35, Low. `references.bib`, `langgraph2026durable`.** The URL now redirects to Persistence. Add an archive URL or the `interrupts` and `functional-api` pages. The claim itself is accurate (section 3).

- **F-36, Low. Artifact and memory file.** The JSON E10 note and the script comment still say "roles and visible text … not tuned". MEMORY.md still says "Proposition 2". Align them with the paper.

- **F-37, Low. `system.tex` first paragraph.** Remove the duplicate node list left over from the figure removal.

- **F-25-residual-b, Low. `introduction.tex`.** "Seldom" is uncited. Cite a source or soften further.

## 7. Integrity assessment

**Plagiarism evidence.** No similarity corpus was available, so comprehensive plagiarism verification was not performed. This is not a plagiarism-free verdict.

8-word shingles vs the `paper/` and `ieee/` drafts, the same normalisation as audits 2 and 3:

| Section | Strict (audit 3) | Strict now | Loose now |
|---|---:|---:|---:|
| introduction | 0.055 | 0.054 | 0.059 |
| related | 0.021 | 0.017 | 0.021 |
| model | 0.101 | 0.102 | 0.143 |
| system | 0.056 | 0.067 | 0.080 |
| evaluation | 0.003 | 0.003 | 0.006 |
| discussion | 0.037 | 0.038 | 0.043 |
| conclusion | 0.027 | 0.027 | 0.026 |
| abstract | 0.014 | 0.014 | 0.012 |
| overall | 0.033 | 0.032 | 0.043 |

- **System:** it rose slightly. The overlapping runs are the team's own earlier descriptions of the same components, for example "Perception turns a capture into a Semantic UI Map …", "an element hidden from the AX tree can still be an exposure" and "behind a rate-limited provider interface". This is same-project text reuse, which is common technical phrasing. Any disclosure of reuse depends on a policy I do not have.
- **`evaluation.tex`:** the section rewritten most is essentially new text.
- **Against `novelty-analysis.md`:** strict 8-word shingles give 0 overlap in every section. Loose 8-word shingles give 4 in related and 5 in evaluation, all column or subject vocabulary.
- **External spot checks:** I searched three distinctive sentences as exact phrases ("a short label-based script beats the shipped DOM channel", "Claim-before-execute thus gives at-most-once only in the second mode" and "a test suite seldom contains a scenario for a button that should not exist"). There were no verbatim matches. I also read the Wayback copy of the LangGraph page and the `interrupts` and `functional-api` pages to check the attributed claims. No unattributed borrowing or citation laundering was found.
- **Not verified:** the full texts of cited works and the web at large.

**Citation integrity.** No fabrication or misattribution was found. See section 4 for what remains unverified.

**AI-style risk: Low to Medium (Indeterminate beyond that).**
- Evidence for the risk: uniform, polished prose and formulaic hedges.
- Evidence against it: precise, checkable specifics, negative results kept (E5, E8, A8's losses, the vacuous hit), and numbers that trace to the JSON.
- Limitation: style does not establish authorship, and a drafting agent is documented in the repo.

**External detector results:** none provided, so none reported.

**Verification limitations.** I did not run `pytest`. I did not run the live Playwright, VLM, Neo4j or Redis pipeline. I did not compile in place; I compiled a scratch copy, and the committed `main.pdf` also reports 20 pages. I did not recount the bibliography total. Prior-art completeness cannot be established by search.

## 8. FINAL verdict and publication readiness

**Score 7.8 / 10, Major Revision (near Minor), Borderline.**

The paper is honest, internally consistent and reproducible at fixture level. Its limits are stated. It reads as a defensible workshop-level contribution that describes a formulation and a prototype, with a small, in-sample evaluation and clearly labelled negative results.

It is **not publication-ready at 8.0** for these reasons:
- Evidence breadth is the cap. There is no independent subject, no real Crawljax/ATUSA baseline and no browser-driven, VLM or hybrid result.
- The two wording issues F-33 and F-34 are cheap to fix and would remove the main honesty gap.
- The artifact is uncommitted and unarchived, and the venue and page limit are unknown.

Two things this audit cannot say: that the system works on real applications, and that any numbers hold up under independent annotation.

## 9. What a human author must still do (blocked items)

1. Replace "pre-registered" with an honest ordering statement (F-33). Qualify A8's E12 results as in-sample, decide whether to add a truth variant that includes the policy-named analytics panel, and mark the consent row as non-discriminating (F-34). Add "on these pages" to the abstract's "beats it".
2. Update the LangGraph bib entry with the archive URL or the `interrupts` and `functional-api` pages (F-35).
3. Align the script comment, the JSON E10 note and MEMORY.md with the paper's wording (F-36). Remove the duplicated node list in `system.tex` (F-37). Cite or soften "seldom".
4. Commit, tag and archive `run_experiments.py` and `experiments.json` with a DOI, and fix the commit hash they cite (F-18/F-24).
5. Obtain at least one genuinely independent subject (open-source, real defects, third-party annotation), and a real Crawljax/ATUSA baseline if possible (F-03).
6. Get Track C to settle the policy-subject vocabulary and the Gemini model identifier (F-14), then run the browser-driven and VLM/hybrid pipeline with a labelled probe set (needs an API key).
7. Run a live Neo4j/Redis/durable-checkpointer crash test to confirm E5 beyond the in-memory simulation. Consider filing the E5 resume finding with Track B.
8. Settle the MATE NEG/REQ cells from the full text, and verify the Memon 2003 pages and the WebArena and OSWorld venue years.
9. Fill in the authors and institution placeholders, name the venue, and fit the page limit.
10. Decide whether to add the four "college references" (not done by instruction).
11. Run a real similarity check and any required AI-use disclosure under the venue's policy. This audit supplies neither.

## 10. Writer handoff (machine-readable, for completeness)

```json
{
  "audit_iteration": 4,
  "iteration_limit": 4,
  "remaining_iterations_after_this": 0,
  "quality_threshold": 8.0,
  "target_venue": "Springer svproc proceedings (software engineering / AI agents); no named venue; page limit unknown",
  "paper_source": {
    "immutable_reference": "docs/report/springer/main.tex + sections/{introduction,related,model,system,evaluation,discussion,conclusion}.tex + references.bib at audit 4 (20 pages, abstract 146 words); data docs/report/data/experiments.json (all keys incl. E11, E12, E13, meta, key_map reproduce identically in-process under PYTHONHASHSEED 0, 1, 3, 12345); script docs/report/experiments/run_experiments.py",
    "write_scope": "docs/report/springer/ only; never touch apps/, tests/, test-apps/, services/, infra/, svproc.cls, .claude/"
  },
  "required_format": {
    "class": "svproc (unmodified, byte-identical to the template zip); \\mainmatter; abstract 70-150 words; bibliographystyle plain + natbib numeric; forbidden: amsthm, modifying svproc.cls"
  },
  "current_score": {
    "overall": 7.8,
    "previous": 7.5,
    "breakdown": {
      "novelty_originality": {"score": 1.0, "max": 2.0, "delta": 0.0},
      "technical_correctness": {"score": 1.7, "max": 2.0, "delta": 0.05},
      "evidence_results": {"score": 1.55, "max": 2.0, "delta": 0.15},
      "literature_citations": {"score": 1.35, "max": 1.5, "delta": 0.05},
      "structure_coherence": {"score": 0.9, "max": 1.0, "delta": 0.0},
      "reproducibility_limitations": {"score": 0.9, "max": 1.0, "delta": 0.05},
      "writing_presentation": {"score": 0.4, "max": 0.5, "delta": 0.0}
    },
    "recommendation": "Major Revision (near Minor)",
    "readiness": "Borderline"
  },
  "resolved_and_verified": ["F-01","F-02 (fake level)","F-04","F-05","F-06","F-07","F-08","F-09","F-10","F-12","F-13","F-15","F-16","F-17 (restatements)","F-19","F-20","F-22","F-23","F-25 (incl. residual page range)","F-26","F-27 (executed; independence not achieved)","F-28 (claim accurate; URL stale, see F-35)","F-29 (paper)","F-30","F-31"],
  "findings": [
    {"id": "F-33", "severity": "Medium", "status": "open", "location": "evaluation.tex 'Three further apps' paragraph and Table 9 caption; script keys",
     "evidence": "'pre-registered' cannot be verified: docs/report untracked, no commit/hash/registry, script and JSON mtimes 6 s apart, README of feature-flag app quotes the button HTML, audit 3 described HTML details",
     "correction": "Replace with 'derived from the README text first; ordering is an authorial statement the artifact cannot evidence'; drop 'pre-registered' from caption, text and JSON/script keys"},
    {"id": "F-34", "severity": "Medium-Low", "status": "open", "location": "evaluation.tex E12 paragraph, Table 9; abstract 'beats it'",
     "evidence": "A8 XPaths written after reading the scored HTML (in-sample); truth omits README-policy-named Advanced Analytics panel and RBAC delete button; consent control circular for A8; A3 vs A8 asymmetric information",
     "correction": "State E12 A8 results are in-sample; add truth variant including the analytics panel or state A8 misses it; mark consent row non-discriminating; qualify abstract"},
    {"id": "F-35", "severity": "Low", "status": "open", "location": "references.bib langgraph2026durable",
     "evidence": "cited URL now redirects to Persistence page; statements confirmed in Wayback snapshot (2025-12-13) and in current interrupts and functional-api pages",
     "correction": "Add archive URL or interrupts/functional-api pages; keep access note"},
    {"id": "F-36", "severity": "Low", "status": "open", "location": "experiments.json E10.note; run_experiments.py XPATH_INVARIANTS comment; MEMORY.md",
     "evidence": "stale 'roles and visible text ... not tuned'; MEMORY.md still says Proposition 2 and 49 entries (not recounted)", "correction": "Align with paper wording"},
    {"id": "F-37", "severity": "Low", "status": "open", "location": "system.tex first paragraph and Orchestration subsection",
     "evidence": "node names listed twice (leftover from removed figure)", "correction": "Remove duplicate list"},
    {"id": "F-25-residual-b", "severity": "Low", "status": "open", "location": "introduction.tex", "evidence": "'seldom contains a scenario for a button that should not exist' uncited", "correction": "Cite or soften"},
    {"id": "F-03", "severity": "High", "status": "partial/blocked", "location": "evaluation.tex", "evidence": "same-project subjects only; no real Crawljax/ATUSA baseline", "correction": "Needs independent subject (author)"},
    {"id": "F-11/F-21/F-32", "severity": "Low-Medium", "status": "partial", "location": "related.tex Table 1", "evidence": "MATE NEG/REQ '?' (bib entry verified via Crossref, abstract names no checks)", "correction": "Settle from full text or keep '?'"},
    {"id": "F-14", "severity": "Medium", "status": "blocked", "location": "system.tex", "evidence": "gemini.py docstring vs _MODEL mismatch", "correction": "Track C"},
    {"id": "F-18/F-24", "severity": "Low", "status": "partial", "location": "artifact", "evidence": "uncommitted, unarchived", "correction": "Author decision"},
    {"id": "F-17", "severity": "Low", "status": "partial", "location": "whole paper", "evidence": "20 pages; limit unknown", "correction": "Fit venue limit"}
  ],
  "must_not_change": [
    "The exploration graph is CYCLIC; never call it a DAG; never prune revisit edges; loop prevention = visited (state_id, action_id) set only",
    "RQ1/RQ3 use fakes and a scripted crawler; never present as end-to-end",
    "REPLAY_SAFE_KINDS = {navigate, click, back}; keep the residual-risk statement",
    "Only report numbers present in data/experiments.json or reproduced by run_experiments.py",
    "Do not edit E1-E13 values to improve results; keep E5 negative result, E8 over-merges, A8's losing cases and the vacuous-hit disclosure",
    "Do not edit anything under test-apps/",
    "Do not invent citations, results or detector scores; do not claim plagiarism-free",
    "Authors remain placeholders; do not modify svproc.cls; do not load amsthm; abstract <=150 words",
    "Do not add the four college references unless the user decides"
  ],
  "blocked_by_missing_evidence": [
    "Independent subject apps and a real Crawljax+ATUSA baseline",
    "End-to-end Playwright to semantic map to audit run (Track C vocabulary, API key)",
    "Live Neo4j/Redis/durable-checkpointer crash test",
    "VLM/hybrid per-polarity accuracy",
    "Gemini model identifier (Track C)",
    "Artifact commit/archive",
    "Authors, venue, page limit",
    "MATE contents, Memon 2003 pages",
    "Similarity corpus; AI-detector results"
  ],
  "previous_iterations": [
    {"iteration": 1, "score": 5.7},
    {"iteration": 2, "score": 6.9},
    {"iteration": 3, "score": 7.5}
  ],
  "iteration_budget": {"threshold": 8.0, "iterations_remaining_after_this": 0, "note": "Iteration limit reached; remaining items need a human author."},
  "writer_invoked": false
}
```

I did not invoke the writer agent. This was the final iteration, and you asked me not to edit repo files.

## Relevant files (all read-only)

- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/sections/evaluation.tex` (F-33, F-34)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/sections/system.tex` (F-37)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/sections/introduction.tex` (F-25-residual-b)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/references.bib` (F-35)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/MEMORY.md` (F-36)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/experiments/run_experiments.py` (E12 derivation and `EXTRA_XPATH`; `XPATH_INVARIANTS` comment)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/data/experiments.json` (E10 note; E12, E13)
- `/home/kr95/Projects/final-year-project/statescout-ai/test-apps/` (the three subjects, untouched)

Sources checked:
- [LangGraph durable execution, Wayback snapshot of 2025-12-13](https://web.archive.org/web/20251213033841/https://docs.langchain.com/oss/python/langgraph/durable-execution)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts.md)
- [LangGraph functional API](https://docs.langchain.com/oss/python/langgraph/functional-api.md)
- [Crossref record for MATE](https://api.crossref.org/works?query.bibliographic=Automated+Accessibility+Testing+of+Mobile+Apps+Eler+Rojas+Ge+Fraser)
- [MATE, IEEE Xplore 8367041](https://ieeexplore.ieee.org/document/8367041)