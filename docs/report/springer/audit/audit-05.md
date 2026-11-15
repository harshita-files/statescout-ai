# Audit report: StateScout Springer paper, iteration 5 (FINAL)

I wrote nothing to the repo. All scratch work (compile copy, rerun script, shingle script, E14 dump) is in the session scratchpad. I called the `e*()` functions in-process, never `main()`, with `PYTHONHASHSEED` 0, 1 and 12345 and `PYTHONDONTWRITEBYTECODE` set.

## 1. Executive verdict

- **Score: 7.8 / 10.** Audit 4 gave 7.8, so there is no net change. The 8.0 threshold is not met.
- **Recommendation:** Major Revision, close to Minor.
- **Readiness:** Borderline.
- **The writer was not invoked.** This is the last audit, and you asked me not to edit repo files.

**Did the 22 pages and the extra references or evidence move the score?** No, not on net.
- Length earned nothing.
- The four college references did not help. One has a wrong year (F-42).
- E14 is a small plus: a more blind protocol and unflattering results, honestly reported. It is offset by an asymmetric required-clause tally, undisclosed fixture defects (F-38, F-39) and an unfinished F-35 fix.

**Three most serious problems**
1. **No independent subject and no browser, VLM or hybrid result (F-03, blocked).** E14 adds more same-project, AI-generated apps, which the paper says "add variety … not independence".
2. **E14 scoring is not even-handed, and the fixtures have undisclosed defects (F-38, F-39).**
   - A8's required-clause results are not put through the same "genuine TP" filter as A3's.
   - A8's cfg-1 hit comes from an unmatchable query.
   - Six of the eight forbidden-violation pages have no inbound link.
   - Several ground-truth and clean-page labels contradict the HTML or the policy text.
3. **Writer claim F-35 is false.** The `langgraph2026durable` bib entry is unchanged. The ordering evidence for E14 is only self-attested, but the paper words that honestly.

## 2. Verification of the writer's claims

| Claim | Result |
|---|---|
| F-33 ("pre-registered") | **Resolved.** The word appears nowhere in `sections/`, `main.tex`, the script or the JSON. The new wording is honest. |
| F-34 (in-sample, truth variant, consent row, abstract) | **Resolved.** The truth variant is stored and reported (A8 1/2, A3 0/2). The consent row is marked non-discriminating. The abstract says "in-sample … on these pages". |
| F-35 (LangGraph entry notes redirect, archive, interrupts page) | **NOT done.** `references.bib` lines 446–451 are unchanged. The note still says "read in search excerpts", with no archive URL and no interrupts page. `revision-matrix-05.md` marks it Resolved. That is incorrect. |
| F-36 (script, JSON, MEMORY aligned) | **Partly.** The script comment and the E10 JSON note are fixed ("not tuned" no longer appears). MEMORY.md is still stale (F-43). |
| F-37 (duplicate node list) | **Resolved.** The four nodes are now listed once. |
| Intro residual (F-25-residual-b) | **Partly.** "seldom" is gone, but the sentence before it still says "Ordinary UI tests **rarely** catch these problems", and it is uncited. |
| E1–E9, E11, E13 identical to stored v4 | **Verified** under all three seeds, against my saved v4 snapshot and the stored JSON. |
| E10/E12 wording and key-name changes only | **Verified.** E10 changed only in `note`. E12 changed only in key renames, `derivation_notes`, `disclosure`, and the added `truth_variant…`, `A8_row_discriminating` and `A8_row_note`. Every numeric value is identical. |
| meta flag | **Verified.** `code_tree_clean_vs_head` went from True to False because the untracked `paper-subjects/` folder exists. `key_map` gained E14. The stored E14 equals my in-process re-run under all three seeds. |
| E14 totals | **Verified.** I re-derived everything from the fixtures and `ground_truth.json`; see section 3. |
| Git state | **Verified.** There are no changes under `apps/`, `tests/` (only the untracked `paper-subjects/`), `test-apps/`, `services/` or `infra/`. Nothing is committed; HEAD is still `4487574`. No new `.pyc` files and no `__pycache__` under `docs/report`. |

## 3. E14 checks

### (1) Can the ordering be checked?

- **Hash:** recomputing `sha256(e14_invariants.py)` gives `4537f85c…6d92`. It matches the `.sha256` file and the JSON `sha256_now`.
- **File times:**
  - `e14_invariants.py` was modified at 10:48:45.299 IST. `e14_invariants.sha256` was modified 7 ms later, at 10:48:45.306.
  - 10:48:45 IST is 05:18:45Z, which is the recorded "UTC timestamp". So the timestamp is just the hash file's creation time.
  - The invariants file has not changed since then. Its mtime equals the hash file's, and its contents match the hash.
  - `run_experiments.py` was last edited at 10:51:25, and the JSON was written at 10:51:38. So the results come after the hash.
- **Ordering relative to the fixtures cannot be shown.** All 46 fixture files (HTML, `policy.*`, `ground_truth.json`, README) were created 10:39:11–10:46:31, before the hash. The timestamp is compatible with "written without opening the HTML" and is not evidence for it.
- **Circumstantial evidence for blindness.**
  - The invariants use only things available from `policy.expected.json` and the directory listing: file names, `expectation_id`s, and policy wording.
  - Several guesses cannot match the HTML: `@id='subscription-level'`, `'Run Payroll'`, and the `admin-dashboard.html`, `billing.html` and `emergency.html` link targets, since nothing links to them.
  - A8 getting only 3/8 forbidden fits a blind author.
  - Nothing in the invariants needs HTML-only knowledge.
- **Honesty of the wording.** Yes. The paper says "the order is self-attested, and the hash shows only that the file was not edited afterwards." The JSON `ordering` field says the same.
- **Minor point:** the paper says "UTC timestamp" without saying it is only a file time. Say so.

### (2) Are the numbers right?

I re-derived the per-clause accounting. All claimed figures match.

| Figure | Result |
|---|---|
| A3 forbidden | 0/8 found, 0 FP |
| A3 required | 4 hits, each on a clause that fires on all 7 pages; 19 FP (5+4+5+5) on listed clean pages; 33 unlisted hits |
| A8 forbidden | 3/8 found (checkout, staff-portal, team), 0 FP |
| A8 required | 3/4 found, 4 FP, 12 unlisted hits |
| Double-negation clauses | all 4 A8 FP and 7 of A3's 19 FP |
| Truth variant, feature-flag app | A8 1/2, A3 0/2 |

The arithmetic is correct. The problems are in how it is tallied and how sound the fixtures are.

**The accounting is not even-handed (F-38, Medium).**
- A3's four required hits are called "coincidental", which is right because the clause fires on every page.
- Table 2's own rule excludes a required-absent hit when the clause also fires on pages that carry the element. Under that rule two of A8's three required hits are also excluded:
  - shop-3 fires on `support.html`, which is listed clean.
  - med-3 fires on `emergency.html` and `appointments.html`, which are listed clean.
- A8's third hit, cfg-1, is vacuous. No fixture HTML contains any `id` attribute at all, so `[@id='subscription-level']` and `[@id='current-plan']` can never match. The clause fires on `settings.html` regardless of content.
- The paper reports "finds 3 of 4 with 4 false positives" and never applies the genuine-TP filter to A8.
- Apart from the two shop-3/med-3 hits (which do discriminate index/dashboard from the pages that carry the link), A8's genuine required recall is 0 or 1 of 4. That depends on how "carry" is read.
- The 33 unlisted A3 hits appear in the text. The 12 unlisted A8 hits do not appear in the paper. They are in the JSON only.
- A8 invariants have a per-page scope (`index.html`, `settings.html`, `all_but_login`). The shipped engine has no page scope, and the Discussion says so ("scoped by role only"). A3 cannot express "the home page must…", so it fires everywhere. The E14 paragraph does not mention this advantage.
- **Net judgement.** "Not counted as FP" is defensible on its own. Most of A8's 12 unlisted hits are real absences under an all-pages reading of a role-only policy. But the unlisted pages are neither truth nor clean, so the reported precision is only as meaningful as the clean lists. Those lists are weak (F-39).

**The "decoy-adjacent" label carries almost no information.**
- It means "the page text contains any 4+-letter content word of the subject". For example, `appointments.html` matches "contact" via "Contact the clinic".
- The clean pages for required clauses are mostly pages that carry the target, or are the target page itself. So "19/19 and 4/4 are decoy-adjacent" is close to tautological.
- Three of A8's four FPs are the target page not linking to itself (`support.html`, `emergency.html`, `password-change.html`).

**Fixture soundness (F-39, Medium).** The apps are static, and ground-truth labels are the generator's assertions.
- **Orphan pages.** I computed inbound `<a>` links. Six of the eight forbidden-violation pages have zero inbound links: `admin-dashboard`, `checkout`, `staff-portal`, `salary-view`, `payroll-calc`, `billing`. The other two (`medical-records`, `team`) are linked.
- **Login pages.** They link nowhere, so no app is crawlable by links from its entry page. This does not matter for static per-page auditing. It matters for the paper's "explores states" framing, and the paper does not say it.
- **Policy versus ground truth, shop-0.**
  - The clause reads "Guests must never see a **link** to the admin dashboard." No link to it exists anywhere in the app.
  - The ground truth marks the page itself as the violation, so the clause is vacuous under its own wording.
- **shop-3.** `products.html` has a Support link, so the policy "users must not fail to find a way to contact support" holds app-wide. The ground truth flags only `index.html`, and the policy never mentions the home page.
- **hr-3.** `dashboard.html` shows "Your Benefit Enrollment Status", yet `benefits.html` is the flagged page.
- **med-3.**
  - `appointments.html` is listed clean, but it has no emergency information, exactly like the flagged `dashboard.html`.
  - Nothing links to `emergency.html` at all.
  - `prescriptions.html` and `medical-records.html` are equally lacking but unlisted.
  - So A8's FP at `appointments.html` is arguably a correct detection.
- **cfg-3.** `settings.html` is listed clean for "modify organization settings", but it has an "Organization" field and a "Save Changes" button.
- **shop-2.** The "Complete Purchase" button is on an ordinary checkout form with empty payment fields. The "violation" is just the normal checkout.
- **Roles.** Pages are role-agnostic static HTML, so role is a nominal filter.
- **No leakage.** The HTML has no comments, `data-tag`, or "violation"/"bug" text (grep found none). The READMEs do not name the violations.
- **Disclosure.** The paper discloses "AI fixture tool, same project, not independence" correctly. It does not disclose any of the fixture defects. It also says "5–7 pages"; every app has exactly 7.

### (3) Comparison framing

- **"A label script beats the shipped DOM channel."** The body sentence is scoped to the stripped original fixture (A3 2 TP and 5 FP, A8 4 and 0). The E14 paragraph that follows honestly gives "a more modest result". The claim is supported but is a low bar. A3 is given policy subjects that by construction match none of the tagger's vocabulary, and the paper itself says so.
- **Abstract.** "an in-sample label-based script beats it on these pages but fails when labels change" is not contradicted by E14. It is now incomplete:
  - It says nothing of E14, where the script finds only 3 of 8 forbidden violations.
  - On E14 the script's failure is wrong guesses, not label changes.
  - The abstract is exactly 150 words, so there is no room. Swap a clause rather than add words.
- **Discussion and Conclusion.** Neither mentions E14. That is not wrong, but it means the unflattering result is not in the take-away.
- **Stale text in Threats.** "knew the labels A8 queries" is not true for E14.
- **Independence.** No overclaim anywhere. The Threats section lists the four generated apps as same-project.

## 4. College references

The Crossref data does not show who supplied these references or whether the authors are related to them.

| # | Crossref / publisher check | Bib entry | Verdict |
|---|---|---|---|
| 4 `sridhar2020rule` | JCTN 17(1) 308–315, 2020, DOI 10.1166/jctn.2020.8667; Sridhar, Parameswaran, Thangavel. The abstract describes rule-based YCbCr fire-pixel detection, tested on images. | Matches. | Correct. The title says "Real Time Videos". |
| 3 `sridhar2020firepixel` | Book chapter, pp. 392–400, DOI 10.1007/978-981-15-6067-5_44; authors Sridhar, Thangavel, Parameswaran; online 2020-09-22, print volume 2021. | Matches (2020). | Correct. The abstract is unavailable (publisher-elided). |
| 1 `sridhar2025cloud` | CPE 37(15–17), e70151, online 2025-06-19, print 2025-07; Sridhar and Sathiya. | Matches. | Correct. |
| 2 `sathiya2025stress` | **Differs.** Crossref gives year 2026, pp. 373–386, DOI 10.1007/978-981-96-9716-8_29, five authors (Sathiya, Anton Tamilselvan, Neranjan, Ashwin, Jayakrishna). Book: *Power Engineering and Intelligent Systems: Proceedings of PEIS 2025, Volume 1*, LNEE vol. 1459, Springer, published 2026. | The bib has year 2025, "Sathiya and others", no pages, and the conference name given as (PEIS). | **Confirmed discrepancy.** |

- **Why the discrepancy exists.** 2025 is the conference year (held 8–9 March 2025 at NIT Srinagar). 2026 is the proceedings publication year. The reference-list year should be the publication year.
- **My judgement on #2.** Using the Crossref/Springer form is right: the year (2026), pages 373–386, the full five authors, and the proceedings title. Keeping the supplied "2025, et al." leaves a known-wrong year in the list (F-42). I could not read the publisher page, because Springer redirected to a login, so I relied on Crossref plus a search result for the conference.
- **Placement and honesty.**
  - The related-work sentence says "adjacent rule-based work, not as support for our approach". That is honest and makes no relevance claim.
  - "rule-based detection over video streams" is checked for #4 only. #3's abstract could not be read, and the #4 abstract describes images.
  - #1 and #2 sit in an unnumbered "Acknowledgments" section that contains only "The reference list additionally includes [35, 33], listed here without further claim."
  - The citations are in a different field from the topic: fire detection, cloud workload forecasting, stress monitoring.
  - Neutrally: a reviewer may read the Acknowledgments note and the off-topic sentence as inserted citations. The transparent wording is the least bad way to include them. They can be removed without changing any result.
  - Whether to keep them is the authors' decision. The citation-integrity cost is the wrong year on #2.
  - The reference list is now 52 entries. The 22 pages are body to page 17, then references.

## 5. Re-run, compile and artifact checks

- **Re-run.**
  - E1_E3, E2, E5, E6, E7, E8, E9, E11 and E13 are identical to the stored JSON and to v4, under seeds 0, 1 and 12345.
  - E10, E12 and E14 equal the stored JSON. E10 and E12 differ from v4 only in the intended wording, key and added-field changes.
  - `meta` equals the stored JSON, with `code_tree_clean_vs_head` False versus True in v4.
- **Compile (scratch copy).**
  - 22 pages; the committed `main.pdf` also has 22.
  - **1 overfull hbox** (2.07 pt, the RQ2 table, lines 175–186). The earlier "0 overfull" no longer holds, though it is visually negligible.
  - 0 undefined references, 0 BibTeX warnings, and one OT1 small-caps font warning.
  - Abstract: **exactly 150 words**. It is within the limit with zero slack.
- **Class and packages.** `svproc.cls` sha256 `ddfc1f23…9560` is identical to the template zip. There is no `amsthm`, and there is no TODO, placeholder or lorem text.
- **Email.** Only in `main.tex`.
- **Reproducibility.** The E14 inputs sit in an untracked folder. The "Environment and artifact" paragraph says the script and JSON are uncommitted, but not that the E14 fixtures are too. It also says "code tree unchanged at run time", while the stored `meta` flag is now False (F-41).

## 6. Plagiarism, AI-style and other integrity checks

- **Plagiarism verification was not comprehensive.** There is no similarity corpus, so this is not a plagiarism-free verdict.
- **8-word shingles vs the `paper/` and `ieee/` drafts, same normalisation as audits 2–4:**

| Section | Strict now | Loose now |
|---|---:|---:|
| introduction | 0.055 | 0.060 |
| related | 0.016 | 0.021 |
| model | 0.102 | 0.143 |
| system | 0.068 | 0.074 |
| evaluation | 0.003 | 0.005 |
| discussion | 0.028 | 0.035 |
| conclusion | 0.024 | 0.022 |
| abstract | 0.013 | 0.012 |
| overall | 0.031 | 0.041 |

- **Interpretation.** These are essentially unchanged from audit 4. Overlap is concentrated in `model` and `system`, which are the team's own earlier descriptions of the same components (same-project reuse). The new E14 text overlaps nothing.
- **Novelty-analysis file.** Strict overlap is 0 in every section. Loose overlap is 4 in related and 5 in evaluation, all vocabulary.
- **External spot checks.** I searched two distinctive new sentences as exact phrases, one from the E14 paragraph. There were no matches.
- **Citation integrity.** No fabrication found. The one inaccurate entry is #2's year and authors (F-42). The LangGraph entry is unchanged and lacks the archive pointer.
- **AI-style risk: Low to Medium (Indeterminate beyond that).** Uniform, polished prose and formulaic hedges raise it. Precise checkable specifics, kept negative results, and numbers that trace to the JSON lower it. Style does not establish authorship.
- **External detector results:** none provided, so none reported.
- **Not verified.**
  - The web at large, and the full text of cited works.
  - #3's abstract.
  - The Springer page for #2.
  - Memon 2003 pages, and the WebArena and OSWorld venue years.
  - Whether the E14 invariants were really written blind. This is only self-attested.
  - No live pipeline, `pytest`, Playwright, VLM, Neo4j or Redis.

## 7. Detailed scoring and audit trail vs 7.8

| Criterion | Score | Max | Change | Justification |
|---|---:|---:|---:|---|
| Novelty and originality | 1.0 | 2.0 | 0 | Still a thin formulation. Positioning is accurate. |
| Technical correctness and methodology | 1.7 | 2.0 | 0 | +0.05 for F-33 and F-34 (wording honest, in-sample stated, truth variant). −0.05 for the F-38 asymmetric accounting and the unmatchable-id vacuity. |
| Evidence, experiments, results | 1.6 | 2.0 | +0.05 | E14 is a more blind protocol and honest modest results, with the hash verified and numbers exact. Capped by same-project AI-generated fixtures, undisclosed orphan pages and ground-truth inconsistencies (F-39), and no independent, browser, VLM or hybrid result. |
| Literature and citation quality | 1.3 | 1.5 | −0.05 | #2 has a known-wrong year; #3's characterisation is unverified; the placement looks inserted. F-35 is not done. |
| Structure, reasoning, coherence | 0.9 | 1.0 | 0 | Duplicate node list fixed. The Acknowledgments-as-citation note is odd. 22 pages, venue limit unknown. |
| Reproducibility and limitations | 0.9 | 1.0 | 0 | Exact re-run and hash protocol. Offset by the untracked E14 inputs, the "code tree unchanged" wording versus meta False, and the uncommitted artifact. |
| Academic writing and presentation | 0.4 | 0.5 | 0 | One 2 pt overfull box; the abstract has zero word slack. |
| **Total** | **7.8** | **10.0** | **0** | |

No score rose because of length, and none rose because of the added references.

## 8. Critical findings

**Carried over:** F-01, F-02 (at fake level), F-04 to F-10, F-12, F-13, F-15, F-16, F-17 (restatements), F-19, F-20, F-22, F-23, F-25, F-26, F-27, F-28 (claim accurate), F-29, F-30, F-31, F-33, F-34 and F-37 are resolved. F-03, F-11/F-21/F-32 and F-18/F-24 are partial. F-14 is blocked. F-35 is open (new status below).

- **F-35, Low, reopened. `references.bib` `langgraph2026durable`.** Not changed despite the matrix. Add the archive URL (Wayback 2025-12-13) or the `interrupts` and `functional-api` pages, and keep the "read as of" note.
- **F-38, Medium. `evaluation.tex`, "Four generated apps".**
  - Evidence: section 3, point (2) above.
  - Fix: apply Table 2's genuine-TP rule to A8 and give A8's genuine required count; state that the cfg-1 hit is vacuous; mention A8's 12 unlisted hits as well as A3's 33; note that A8 invariants have page scope the engine lacks.
- **F-39, Medium. Same paragraph and Threats.**
  - Evidence: section 3, point (2) above.
  - Fix:
    - Add one or two sentences saying that the ground truth is the generator's own assertion and is unvalidated.
    - Say that most violation pages are not linked from any page.
    - Say that several clean-page labels contradict the policy or the HTML.
    - Drop or qualify the "decoy-adjacent" sentence.
    - Do not edit the fixtures or the stored numbers.
- **F-40, Low. `evaluation.tex`, E14.** Say the timestamp is a file time and that all fixtures existed before it (honest wording otherwise).
- **F-41, Low. Several spots.**
  - "5–7 pages" should read 7.
  - Threats "knew the labels" should be qualified for E14.
  - "code tree unchanged at run time" contradicts meta False, which the untracked E14 folder causes.
  - The artifact paragraph should say the E14 fixtures are untracked.
  - The abstract omits the E14 3/8 result.
- **F-42, Low to Medium. `references.bib`, `sathiya2025stress`.** The year should be 2026, with pp. 373–386, all five authors, and the title *Power Engineering and Intelligent Systems: Proceedings of PEIS 2025, Volume 1* (the conference year 2025 can be noted in the text). Also soften "rule-based detection over video streams" for #3, since its abstract was not read. Consider whether the Acknowledgments citation note is needed.
- **F-43, Low. Housekeeping.**
  - MEMORY.md is stale:
    - Section 1 says authors are UNKNOWN.
    - Section 7 says 20 pages.
    - Section 6 says 53 entries, but the bib has 52.
    - The revision history has no v5 row.
    - It still says the college references were "NOT added" in places.
  - One overfull hbox (2 pt).
  - The intro "rarely catch" claim is uncited.

## 9. Integrity assessment summary

| Area | Result |
|---|---|
| Plagiarism evidence | None found; verification not comprehensive. |
| Citation integrity | No fabrication or misattribution found. One known-wrong year (#2), one unverified characterisation (#3), and an unfinished LangGraph entry. |
| AI-style risk | Low to Medium (Indeterminate). |
| External detectors | None provided. |
| Verification limits | See section 6, "Not verified". |

## 10. FINAL verdict

**7.8 / 10, Major Revision (near Minor), Borderline.** The paper is honest, reproducible at fixture level, and its limits are stated. The E14 additions are fairly reported where they are unflattering, but they are not even-handed (F-38) and rest on weak fixtures (F-39). The threshold of 8.0 is not reached. The remaining gap is evidence independence and breadth, which prose cannot fix.

## 11. What the human authors must still do

1. Decide whether to keep the four college references. If you keep #2, change its year to 2026 with the Crossref/Springer fields (F-42).
2. Fix the LangGraph bib entry (F-35). Fix the E14 text (F-38, F-39, F-40, F-41). Update the abstract to mention the E14 result within 150 words.
3. Obtain at least one independent subject: open-source, real defects, third-party annotation. A real Crawljax/ATUSA baseline would help (F-03).
4. Settle the policy-subject vocabulary and the Gemini identifier with Track C. Run the browser-driven and VLM/hybrid pipeline with a labelled probe set (needs an API key) (F-14).
5. Commit, tag and archive `run_experiments.py`, `experiments.json`, `e14_invariants.py`, the `.sha256` file and the `paper-subjects/` fixtures. Fix the commit hash they cite (F-18/F-24). If ordering evidence matters, commit the invariants before opening any HTML.
6. Run a live Neo4j/Redis/durable-checkpointer crash test to confirm E5 beyond the in-memory simulation.
7. Settle MATE NEG/REQ from the full text. Verify Memon 2003 pages and the WebArena and OSWorld venue years.
8. Name the venue and fit its page limit. Run a real similarity check and any AI-use disclosure the venue requires.
9. Refresh MEMORY.md (F-43).

## 12. Writer handoff (machine-readable)

```json
{
  "audit_iteration": 5,
  "iteration_limit": 5,
  "remaining_iterations_after_this": 0,
  "quality_threshold": 8.0,
  "target_venue": "Springer svproc proceedings (SE / AI agents); no named venue; page limit unknown",
  "paper_source": {
    "immutable_reference": "docs/report/springer/main.tex + sections/{introduction,related,model,system,evaluation,discussion,conclusion}.tex + references.bib (22 pages, abstract 150 words, 52 bib entries); data docs/report/data/experiments.json; script docs/report/experiments/run_experiments.py; docs/report/experiments/e14_invariants.py sha256 4537f85c18805d41c3d2c51561abe751ce82ff4e7052b1417f29951403d96d92",
    "write_scope": "docs/report/springer/ only; never touch apps/, tests/, test-apps/, services/, infra/, svproc.cls, .claude/"
  },
  "required_format": {
    "class": "svproc (unmodified, byte-identical to template zip, sha256 ddfc1f23...9560); \\mainmatter; abstract 70-150 words (now exactly 150); bibliographystyle plain + natbib; forbidden: amsthm, modifying svproc.cls"
  },
  "current_score": {
    "overall": 7.8,
    "previous": 7.8,
    "breakdown": {
      "novelty_originality": {"score": 1.0, "max": 2.0, "delta": 0.0},
      "technical_correctness": {"score": 1.7, "max": 2.0, "delta": 0.0},
      "evidence_results": {"score": 1.6, "max": 2.0, "delta": 0.05},
      "literature_citations": {"score": 1.3, "max": 1.5, "delta": -0.05},
      "structure_coherence": {"score": 0.9, "max": 1.0, "delta": 0.0},
      "reproducibility_limitations": {"score": 0.9, "max": 1.0, "delta": 0.0},
      "writing_presentation": {"score": 0.4, "max": 0.5, "delta": 0.0}
    },
    "recommendation": "Major Revision (near Minor)",
    "readiness": "Borderline"
  },
  "resolved_and_verified": ["F-33", "F-34", "F-37", "F-36 (script and JSON only)", "all earlier resolved items listed in section 8"],
  "findings": [
    {"id": "F-35", "severity": "Low", "status": "open (writer claim false)", "location": "references.bib langgraph2026durable", "evidence": "entry unchanged, no archive URL or interrupts page", "correction": "add archive URL / interrupts and functional-api pages; keep access note"},
    {"id": "F-38", "severity": "Medium", "status": "open", "location": "evaluation.tex 'Four generated apps (E14)'", "evidence": "A8 required hits not filtered by Table 2 genuine-TP rule (shop-3, med-3 fire on listed clean pages); cfg-1 hit vacuous (no id attribute exists in any fixture HTML); A8's 12 unlisted hits not in the text while A3's 33 are; A8 has page scope the engine lacks", "correction": "apply the same rule to both arms; report A8 genuine required count; state vacuity and unlisted counts; note page scope"},
    {"id": "F-39", "severity": "Medium", "status": "open", "location": "evaluation.tex E14 paragraph; Threats", "evidence": "6 of 8 forbidden-violation pages have no inbound link; login pages link nowhere; shop-0 clause says 'link' but no link exists; shop-3 satisfied app-wide; hr-3 dashboard shows status; med-3 appointments listed clean but lacks emergency info; cfg-3 settings listed clean but has Organization field and Save; 'decoy-adjacent' near-tautological; role is nominal; ground truth is the generator's assertion", "correction": "disclose fixture limitations; drop or qualify decoy-adjacent; do not edit fixtures or numbers"},
    {"id": "F-40", "severity": "Low", "status": "open", "location": "evaluation.tex E14 / JSON protocol.ordering", "evidence": "UTC timestamp equals the .sha256 file creation time (7 ms after the .py), after all fixtures existed", "correction": "say it is a file time and cannot show ordering"},
    {"id": "F-41", "severity": "Low", "status": "open", "location": "evaluation.tex; abstract", "evidence": "'5-7 pages' (all are 7); Threats 'knew the labels' not true for E14; 'code tree unchanged at run time' vs meta False; E14 fixtures untracked; abstract omits E14 3/8", "correction": "fix wording; swap abstract clause within 150 words"},
    {"id": "F-42", "severity": "Low-Medium", "status": "open", "location": "references.bib sathiya2025stress; related.tex; Acknowledgments", "evidence": "Crossref/Springer: 2026, pp. 373-386, five authors, Proceedings of PEIS 2025 Vol. 1, LNEE 1459; bib has 2025 and 'others'; #3 'rule-based' not verified from abstract", "correction": "use the Crossref form; soften #3 characterisation; authors decide on keeping the Acknowledgments note"},
    {"id": "F-43", "severity": "Low", "status": "open", "location": "MEMORY.md; RQ2 table; introduction.tex", "evidence": "stale authors/pages/entry count/college-reference status; 1 overfull hbox 2.07 pt; 'rarely catch' uncited", "correction": "refresh MEMORY; soften or cite intro claim"},
    {"id": "F-03", "severity": "High", "status": "partial/blocked", "location": "evaluation.tex", "evidence": "same-project subjects only; no real Crawljax/ATUSA baseline", "correction": "author must supply independent subject"},
    {"id": "F-14", "severity": "Medium", "status": "blocked", "location": "system.tex", "evidence": "gemini.py docstring vs _MODEL mismatch", "correction": "Track C"},
    {"id": "F-18/F-24", "severity": "Low", "status": "partial", "location": "artifact", "evidence": "uncommitted, unarchived; E14 fixtures untracked", "correction": "author decision"},
    {"id": "F-11/F-21/F-32", "severity": "Low-Medium", "status": "partial", "location": "related.tex Table 1", "evidence": "MATE NEG/REQ '?'", "correction": "settle from full text or keep"},
    {"id": "F-17", "severity": "Low", "status": "partial", "location": "whole paper", "evidence": "22 pages; limit unknown", "correction": "fit venue limit"}
  ],
  "must_not_change": [
    "The exploration graph is CYCLIC; never call it a DAG; never prune revisit edges; loop prevention = visited (state_id, action_id) set only",
    "RQ1/RQ3 use fakes and a scripted crawler; never present as end-to-end",
    "REPLAY_SAFE_KINDS = {navigate, click, back}; keep the residual-risk statement",
    "Only report numbers present in data/experiments.json or reproduced by run_experiments.py",
    "Do not edit E1-E14 values or e14_invariants.py to improve results; keep E5 negative result, E8 over-merges, A8 losing cases, the vacuous-hit disclosure and the E14 unflattering results",
    "Do not edit anything under test-apps/ or tests/fixtures/orchestrator/paper-subjects/",
    "Do not invent citations, results or detector scores; do not claim plagiarism-free; do not claim E14 ordering is proven",
    "Do not claim independence for any subject; do not claim relevance for the four college references",
    "Do not modify svproc.cls; do not load amsthm; abstract <= 150 words"
  ],
  "blocked_by_missing_evidence": [
    "Independent subject apps and a real Crawljax+ATUSA baseline",
    "End-to-end Playwright to semantic map to audit run (Track C vocabulary, API key)",
    "Live Neo4j/Redis/durable-checkpointer crash test",
    "VLM/hybrid per-polarity accuracy",
    "Gemini model identifier (Track C)",
    "Artifact and fixture commit/archive; anchored ordering evidence for E14",
    "Venue and page limit",
    "MATE contents, Memon 2003 pages, #3 abstract, Springer page for #2",
    "Similarity corpus; AI-detector results"
  ],
  "previous_iterations": [
    {"iteration": 1, "score": 5.7}, {"iteration": 2, "score": 6.9}, {"iteration": 3, "score": 7.5}, {"iteration": 4, "score": 7.8}
  ],
  "iteration_budget": {"threshold": 8.0, "iterations_remaining_after_this": 0, "note": "Final audit. Remaining items need new evidence or author decisions; F-35, F-38 to F-43 are wording and housekeeping fixes."},
  "writer_invoked": false
}
```

## Relevant files (all read-only)

- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/sections/evaluation.tex` (F-38, F-39, F-40, F-41)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/references.bib` (F-35, F-42)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/sections/related.tex` (college references #3 and #4)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/sections/conclusion.tex` (Acknowledgments note)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/main.tex` (abstract)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/MEMORY.md` (F-43)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/audit/revision-matrix-05.md` (F-35 claim contradicted)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/experiments/e14_invariants.py`, `e14_invariants.sha256`, `run_experiments.py`
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/data/experiments.json`
- `/home/kr95/Projects/final-year-project/statescout-ai/tests/fixtures/orchestrator/paper-subjects/` (fixtures, untouched)

Sources checked:
- [Crossref: JCTN fire detection, #4](https://api.crossref.org/works/10.1166/jctn.2020.8667)
- [Crossref: ICICV fire pixel chapter, #3](https://api.crossref.org/works/10.1007/978-981-15-6067-5_44)
- [Crossref: PEIS stress chapter, #2](https://api.crossref.org/works/10.1007/978-981-96-9716-8_29)
- [Crossref: PEIS 2025 proceedings book record](https://api.crossref.org/works/10.1007/978-981-96-9716-8)
- [Springer PEIS 2025 Volume 1](https://link.springer.com/978-981-96-9716-8)