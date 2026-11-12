# Audit report: StateScout Springer paper (iteration 2 of 4)

I wrote no repo files. Scratch artifacts (a compile copy, the shingle and Crossref scripts, and the re-run script) are in the session scratchpad. `git status` is identical to the start: only the staged `.claude/hooks/track_b_paths.py` change and the untracked `.claude/agents/*` and `docs/report/` entries. Nothing under `apps/`, `tests/`, `test-apps/`, `services/` or `infra/` changed. I ran `run_experiments.py` only as an in-process import and never called `main()`, so it wrote nothing.

## 1. Executive verdict

- **Overall score: 6.9 / 10** (audit 1: 5.7; +1.2). Threshold 8.0 is not met.
- **Recommendation: Major Revision.** It is no longer a rewrite problem. What remains is mostly evidence strength, plus a few new factual slips.
- **Publication readiness: Borderline.** It is plausible as an honest, fixture-level workshop or short paper. It is not ready as a full research paper.

**Three most serious problems now**
1. **F-03 (High, carried, partly blocked).** There is still one app, authored by the same people as the tool. The E9 "baseline" cannot lose: it reads the same `data-tag` encoding that the mutator writes and that the oracle reads. "64/64" is guaranteed, and the paper correctly says so. No independent baseline or second subject exists.
2. **F-19 (Medium, new, factual).** `system.tex:41` says the checkpointed dictionary holds "claimed pairs". `ExplorationState` in `state.py` has only a `visited_pairs` counter. The claim set lives in `GraphPort` (Redis). The same section says the claim set is in Redis, so the paper contradicts itself. It also hides why checkpoint and claim set can diverge, which is the E5 finding.
3. **F-20 and F-21 (Medium, new).** Two issues.
   - The RQ5 pooled counts (246/75/77/309) are 64 variants of the same six pages, not independent samples. "At scale" overstates them.
   - Two Table 1 cells remain "?" although a fetched source settles them (axe-core NEG, ZAP AE), and the accompanying sentence "fixed rules of one polarity each" is wrong for axe-core.

**Checks that passed**
- The stored JSON reproduces exactly: E1_E3, E2, E5, E6, E7, E8 and E9 are all IDENTICAL. E1–E4 match the audit-1 numbers: 4/0/0; 2/5/2 (P 0.286, R 0.5, F1 0.364); 3/0/1; 2/0/2; 300 naive vs 6 normalized ids.
- Meta: Python 3.13.13, LangGraph 1.2.10, HEAD 4487574, code tree clean at run time.
- The paper compiles in a scratch copy: 20 pages, no overfull boxes, no undefined references, one OT1 small-caps warning. The abstract is 146 words (limit 150). `svproc.cls` is untouched and `amsthm` is not loaded.
- Internal leaks are gone: no "track", "sub-team", "novelty analysis" or "college". Authors remain placeholders.
- The graph is called cyclic throughout, with no DAG wording and no back-edge pruning. `click` is stated as replay-safe, with the residual risk. RQ1/RQ3 are never presented as end-to-end.

## 2. Verification of the writer's claims

| Claim | Result |
|---|---|
| E1–E4 unchanged | Verified against audit-1 values and the re-run. |
| E5: 11 pairs, 0 duplicates, 9 replays, 21 steps | Verified, including the 10-times execution of *index→login* (1 frontier plus 9 replay). |
| E5: crash after claim re-attempted at 11/11 positions | Verified in JSON and in code. |
| E5: 3/22 incomplete | Verified (fresh-crawler rows: 2 plus 1). |
| E6: 1.00/1.00/1.00 | Verified. |
| E7: 802 runs, 0 violations | Verified (200+200+1 per mode, times 2). |
| E8: 8/12 edits change the id | Verified. |
| E9: 64 mutants, baseline 64/64 | Verified. |
| 77/246 and 309 false alarms | Follow from the data. |
| Table 1 reduced to AE POL NEG REQ ROLE MM, axe-core and ZAP added | True. |
| Bib corrected from Crossref | True for the checked entries. |

**E5 against the real code**

The interpretation is correct.
- In `graph_runner.act`, the claim (`mark_visited`) and the action sit in one node.
- A raised exception means the checkpoint still holds the pre-act state, with the candidate still in the frontier.
- Resume re-runs `act`, which pops the candidate and calls the idempotent `mark_visited` again. Nothing calls `is_visited`, so it re-fires the action.
- The code comment (and ADR-001 decision 3) says resume treats such a pair as done-but-unrecorded. E5 contradicts that comment, which is a real Track B finding.
- The edge-write crash is correctly 0/11: `next_bundle` is checkpointed, so `observe` only re-persists the edge.
- No existing test injects a crash between claim and edge. I grepped `tests/`, and `test_poc.py:195` covers only a failed action still claiming its pair.
- Wording: "attempts, not effects" is the right claim, "11/11" is correctly scoped to an in-memory checkpointer and a fake browser, and the paper asks for a durable-checkpointer test. There is no material overclaim or underclaim, with three small caveats.
  - The 11 positions share one mechanism, so "11/11" is not statistical strength (F-22).
  - "Restart from the claim set never continues" holds because the seed `index` has exactly one action. With two seed actions the restart would claim the unclaimed one and explore its subtree. The paper states it as general (F-22).
  - The "3/22" fresh-browser cases occur only when the loop believes the browser is already on the candidate's state (`landed_at == from_state_id`), so no replay happens. The paper's explanation, a browser not where the checkpoint says, is correct.

**E6 and E9 tautology**
- **E6.** `fake.audit` and `negation.audit.audit` are independent implementations, so A1 vs A2 genuinely tests the production audit. Both still consume `fake.analyze`, which reads `data-tag`. That is the encoding the ground truth is written in, so 1.00 is near-guaranteed. The paper says so, and this is a legitimate "consistency check".
- **E9.** The mutation ledger is independent of the audit code but not of the encoding. A2 and A6 both read `data-tag`, and the mutator writes `data-tag`. The paper admits it ("as expected… no detection advantage"). The informative parts are:
  - A3's 0/64 exact matches.
  - The three rename mutants, where A2 and A6 fail identically.
  - The role-scope check. I confirmed `policy.json`: debug-panel and skip have `roles: []`, so the admin run correctly yields exactly those two.
- **E7.** This is a unit test of `audit.py` against its own algebra. The paper says "confirms the production engine is monotone and antitone", which is honest. The word "falsifiable" is mildly generous, since only an implementation bug such as substring matching could fail it.

**DOM-channel claims.** 77/246 forbidden found and 309 false required-absent alarms follow from `pooled_counts`: fp_R 309 = 6 pages × 64 mutants − 75 coincidental hits. Only the "at scale" framing and the pooling are objectionable (F-20).

## 3. Detailed scoring

| Criterion | Score | Max | Change | Justification |
|---|---:|---:|---:|---|
| Novelty and originality | 1.0 | 2.0 | +0.1 | Positioning is now honest and engages axe-core, ZAP and ATUSA. The ATUSA wording is supported by the full text: XPath/JS preconditions, a "No Error Messages in DOM" invariant, structure invariants. The contribution is still a thin formulation (a typed polarity field, a role scope, a vocabulary). Proposition 2 is correctly demoted. The E5 resume finding is useful but engineering, not novelty. |
| Technical correctness and methodology | 1.5 | 2.0 | +0.4 | F-04, F-07, F-09 and F-06 are fixed. Proposition 1 is correctly narrowed. The E5 interpretation is right. Deductions: the "claimed pairs in checkpoint" error (F-19), the generalization in F-22, and D=3 in the 33 bound being the observed depth, not the configured `depth_limit=10` (F-23). |
| Evidence, experiments, results | 1.2 | 2.0 | +0.4 | New, reproducible and code-grounded results: E5 (a genuine negative result), E6, E7, E8 (honest over-merge findings) and E9. Held back by one app, non-independent mutants, a self-authored baseline sharing the encoding, no end-to-end or live run, and no variance or CIs (they are deterministic). |
| Literature and citation quality | 1.2 | 1.5 | +0.1 | I verified about 35 of 45 entries and found no fabrication. See section 5. Deductions: avoidable "?" cells (F-21), missing pages on a few entries, one over-attributed claim (F-25), and the VisionDroid/Trident naming. |
| Structure, reasoning, coherence | 0.8 | 1.0 | +0.1 | Leaks are removed and limitations are consolidated in Sect. 4.7. Discussion and Conclusion still partly restate the results. The body grew from 14 to 16 pages. |
| Reproducibility and limitations | 0.8 | 1.0 | +0.1 | Versions, commit and seed attribution are recorded, and the JSON reproduces. But the whole `docs/report/` tree, including the script and JSON, is untracked, and the cited commit precedes it. There is no archive or DOI. The paper gives no map from its arms and RQs to JSON keys (F-24). |
| Academic writing and presentation | 0.4 | 0.5 | 0 | Fluent and precise. Some formulaic hedging remains. |
| **Total** | **6.9** | **10.0** | **+1.2** | |

**Score audit trail versus 5.7**
- +0.1 novelty: axe-core, ZAP and ATUSA are engaged accurately. Nothing new was shown about the contribution itself.
- +0.4 technical: F-04, F-06, F-07, F-09 verified fixed. F-19, F-22 and F-23 hold it back.
- +0.4 evidence: E5, E6, E7, E8 and E9 verified. The tautology limits and the F-03 blockers cap it.
- +0.1 literature: the checked bib is clean and the F-12 prior art was added. F-21 and F-25 remain.
- +0.1 structure: F-16 resolved and F-17 partly resolved.
- +0.1 reproducibility: versions and commit recorded and the JSON reproduces. The artifact is unarchived and untracked.
- 0 writing.
- No criterion was raised for length. The paper grew from 19 to 20 pages, and the added tables carry real data.

## 4. Critical findings

Status of the 18 earlier findings, as I verified them:

| ID | Status | Notes |
|---|---|---|
| F-01 | Resolved | Shared encoding disclosed. |
| F-02 | Resolved at fake level | Live Neo4j/Redis/browser run blocked. |
| F-03 | Partial | Severity lowered to High (claims now fixture-level). |
| F-04 | Resolved | Checked in the intro, Sect. 3.3 and related work. |
| F-05 | Resolved | |
| F-06 | Resolved | |
| F-07 | Resolved | SAFE column dropped; proposition renamed and scoped. |
| F-08 | Resolved with caveat | E7 is an engine unit test. |
| F-09 | Resolved | |
| F-10 | Resolved | |
| F-11 | Partial | Residual folded into F-21. |
| F-12 | Resolved | |
| F-13 | Resolved | Minor residue in F-25. |
| F-14 | Blocked | Needs Track C. |
| F-15 | Resolved | |
| F-16 | Resolved | |
| F-17 | Partial | |
| F-18 | Partial | |

My count is 13 resolved, 4 partial and 1 blocked, against the writer's 12/5/1. I count F-13 as resolved and the writer counted it partial; I count F-02 as resolved at fake level.

**New and open findings**

- **F-19, Medium. `system.tex:41`.**
  - Evidence: the text says the checkpointed dictionary holds "frontier, claimed pairs, discovery order, skips". `ExplorationState` has no claim set, only a counter. The claim set is behind `GraphPort`.
  - Why it matters: it contradicts the paper's own Redis statement and obscures the mechanism behind the E5 result.
  - Correction: say that the checkpoint holds the frontier and counters while the claim set lives in the graph store. Add a sentence that the two are separate stores, which is why resume does not re-consult the claim set.
- **F-20, Medium. `evaluation.tex` RQ5, Table 2 arms.**
  - Evidence: the "246 + 75 planted" and "77 of 246 / 309" figures pool 64 variants of six pages. The 309 is 6×64−75 and the 77 comes from one capability path. "Reproduces … at scale" overstates it.
  - Correction: report per-clause-type counts per mutant family, not pooled. Replace "at scale" with "on 64 variants of the same pages; counts are not independent". Add an independent baseline (see section 7).
- **F-21, Medium. `related.tex` Table 1 and the paragraph after it.**
  - Evidence: I fetched the axe `marquee` rule: "`<marquee>` elements must not be present". That is a forbidden-element rule, so axe-core NEG should be ✓. ZAP has a spider, so AE "?" is easily resolved. "axe-core and ZAP supply fixed rules of one polarity each" is wrong for axe-core. Its `bypass` rule is required-presence and `marquee` is forbidden-presence. Also, `bypass` accepts a heading or landmark in place of a skip link, which weakens the "R1 oracle" claim.
  - Correction: re-read the rules, mark with a cited source, and reword the sentence. Keep "no row combines…" scoped to the table. Also decide the MATE "?" cells. Its abstract mentions missing-label checks, which would be a REQ-type check.
- **F-22, Low–Medium. Sect. 4.2, Table 4 and discussion.**
  - Evidence: the "claim set only" result depends on `index` having one action (`max_second_run_pairs` = 0 at every position). "Every action of the seed is already claimed" is a fixture fact stated as a general one. The 11 positions are not independent samples.
  - Correction: say "on this fixture, whose seed has one action". Add a fixture variant with two seed actions if feasible. Do not present 11/11 as statistical.
- **F-23, Low. Sect. 3.2 and Sect. 4.2.** The "33" bound uses D=3 (observed maximum depth). The configured `depth_limit` is 10. Say "D = observed depth 3".
- **F-24, Low. Reproducibility.**
  - Evidence: `docs/report/` is untracked, and commit 4487574 does not contain the script or JSON. The paper does not map arms and RQs to JSON keys (E1…E9). The LangGraph msgpack deserialization warnings are unmentioned. `revision-matrix-02.md` cites stale table numbers (Table 6/7 versus actual 5/6).
  - Correction: commit and tag the artifact (author decision), add a key-to-RQ mapping, and fix the matrix numbers.
- **F-25, Low. Citations.**
  - Over-attribution: "WebArena, Mind2Web, OSWorld and SeeAct point to grounding as the main obstacle". I could not verify this for WebArena (unverified).
  - Missing pages: Stoat 245–256, WebMate 55–69, Yandrapally 186–197, nl2spec 383–396, NL2LTL 16428–16430 (Crossref values).
  - VisionDroid was renamed Trident in arXiv v2, which the table does not say.
  - "Sun et al. … test whether privileged pages can be forced" is loose. The abstract describes static source analysis.
  - Not independently verified: Noseevich pages 11–18, CREPE pages 10910–10921, WebArena, Mind2Web, SeeAct, OSWorld, ARO.
- **F-26, Low. `system.tex` Perception.** "The configured identifier and the module's documentation disagree on the version, so we name none" is a note to self. It belongs in an issue, not the paper. Reword to "a Gemini Flash model" and file the mismatch with Track C (F-14).
- **F-17 (carried), Low.** The paper is 20 pages with a limit that is still unknown. Discussion and Conclusion still restate results.

## 5. Integrity assessment

**Plagiarism evidence.** No similarity corpus was available, so comprehensive verification was not performed. This is not a plagiarism-free verdict.
- **Mechanical 8-word shingles vs the `paper/` and `ieee/` drafts.** My normalization is stricter than audit 1's (it strips LaTeX commands, math and citations), so the numbers are not strictly comparable. A looser pass gave similar results.

| Section | Strict | Loose |
|---|---:|---:|
| introduction | 0.054 | 0.056 |
| related | 0.023 | 0.032 |
| model | 0.101 | 0.166 |
| system | 0.056 | 0.067 |
| evaluation | 0.003 | 0.008 |
| discussion | 0.052 | 0.053 |
| conclusion | 0.062 | 0.040 |
| abstract | 0.014 | n/a |

  Overall it is about 3.8% of shingles. Audit 1's baseline was 3–18%, and only `model` still sits near the top of that range, from reused definitions. `evaluation` is essentially new text.
- **Against `novelty-analysis.md`.** 8-word shingles: 0 in every section except related, which has 4 on the loose pass and 0 on the strict. 7-word shingles: 0–5 per section on the loose pass (introduction 1, related 5). Audit 1 found 21 in related. This is lower, so self-reuse has fallen. It was never external copying.
- **External spot checks.** Six distinctive sentences from the introduction, model and related work gave no matches (two of them on the web only through unrelated pages). Full text compared where reachable: ATUSA (TSE 2012). Abstracts compared: Sun et al., Doupé et al., Kea, BACScan, Stoat, AXNav, UIGuard, WebTestPilot, axe `bypass` and `marquee`, ZAP rule 10023 and ZAP users.
  - The related-work sentences are paraphrases with citations attached. For example, BACScan's "feedback-driven oracle on read and modify operations" tracks the abstract's phrase "feedback-driven oracle" and its read/modification wording, and is cited. No unattributed borrowing or citation laundering was found.
- **Not verified:** full text of nearly all cited papers, and the web at large.

**Citation integrity.** About 35 of 45 entries were checked at some level, against 8 of 40 in audit 1. I found no fabricated or misattributed entry.
- **Crossref DOI match (20)** on title, year, pages, volume/issue and author count: crawljax, invariant, webmate, yandrapally, sapienz, stoat, droidbot, humanoid, kea, gptdroid, autodroid, axnav, webtestpilot, li2014, mace, bacscan, barr, uiguard, nl2spec, nl2ltl. WebTestPilot is PACMSE 3(FSE) 1933–1956, correct.
- **arXiv or web (about 15):** visiondroid (v2 title and 9 authors ✓), auitestagent ✓, bacfuzz ✓ (still under review), stwebagentbench ✓ (ICLR 2026), droidagent (ICST pp. 129–139 ✓), mate (ICST pp. 116–126 ✓), ape (ICSE pp. 269–280 ✓), memon2000 (FSE pp. 30–39 ✓), memon2003 (venue ✓, pages not shown), doupe and sun2011 (abstract), axe `bypass`, ZAP 10023, ZAP users, WCAG 2.4.1.
- **Writer's corrections confirmed:** WebTestPilot, BACScan pages, VisionDroid version, and the Kea, Humanoid, GPTDroid, AutoDroid, AXNav, UIGuard and DroidAgent pages.
- **Not independently verified:** see F-25.

**AI-style risk: Low to Medium (Indeterminate beyond that).**
- Evidence: fluent and uniform prose, formulaic hedges ("deliberately narrower", "should be read as"), and repeated limitation statements. Against that, there are many checkable specifics, honest negative results (the E5 contradiction, the over-merges), and every number traces to JSON. I found no fabricated detail.
- Limitation: style cannot establish authorship, and the writer is a documented drafting agent. External detector results: none were provided, so none are reported.

**Verification limitations.** I did not run `pytest`. I did not run the live Playwright, VLM or Neo4j/Redis pipeline. I did not compile in place. I did not fetch full texts of cited papers other than ATUSA. I did not verify the REQ/NEG status of MATE or AXNav beyond abstracts and the writer's "?". Prior-art completeness cannot be established by search.

## 6. Revision plan (ranked)

**Factual corrections:** F-19, F-23, F-22 (wording), F-26.

**New experiments** (feasible within the 2 remaining iterations, no new subject app needed):
1. An independent baseline for F-03/F-20. Write the invariant as XPath over roles and visible text (for example `//a[normalize-space()='Admin']`), not `data-tag`. Run it, A2 and A3 on a copy of the fixture whose `data-tag` attributes are stripped or renamed, built in memory. This makes the baseline comparison non-tautological.
2. A two-seed-action fixture variant for F-22.
3. Report RQ5 per mutant family, not pooled.

**Source verification:** F-21 (axe `marquee`, ZAP spider and MATE cells), F-25 (pages, WebArena claim, Trident naming).

**Structural:** trim Discussion and Conclusion restatements (F-17), and add the artifact key map and commit/tag (F-24).

**Stylistic:** reduce formulaic hedges.

## 7. What score is realistically reachable

- **Without extra subject apps and a real baseline:** about 7.3–7.6 after the plan above. Evidence caps near 1.4, novelty near 1.1, technical near 1.7.
- **Best case without them:** about 7.8, if the independent XPath baseline and a live Playwright run of `broken-admin` are added. The live run needs the Track C vocabulary decision.
- **8.0 or higher is not reachable by prose or small experiments.** It needs at least two independently authored subject applications, ideally open-source with real defects, and a real Crawljax+ATUSA baseline or an equivalent. These are author and orchestrator decisions.

## 8. Writer handoff (machine-readable)

```json
{
  "audit_iteration": 2,
  "iteration_limit": 4,
  "remaining_iterations_after_this": 2,
  "quality_threshold": 8.0,
  "target_venue": "Springer svproc proceedings (software engineering / AI agents); no named venue; page limit unknown",
  "paper_source": {
    "immutable_reference": "docs/report/springer/main.tex + sections/{introduction,related,model,system,evaluation,discussion,conclusion}.tex + references.bib at audit time (20 pages compiled); data docs/report/data/experiments.json reproduced IDENTICAL for E1_E3,E2,E5,E6,E7,E8,E9; script docs/report/experiments/run_experiments.py",
    "write_scope": "docs/report/springer/ plus docs/report/data/ and docs/report/experiments/ only for authorised new experiments; never touch apps/, tests/, test-apps/, services/, infra/, svproc.cls, .claude/"
  },
  "required_format": {
    "class": "svproc (unmodified); \\mainmatter; abstract 70-150 words (now 146); bibliographystyle plain + natbib numeric; packages allowed: url helvet courier graphicx multirow booktabs amsmath amssymb natbib tikz; forbidden: amsthm, modifying svproc.cls; captions: tables above, figures below"
  },
  "current_score": {
    "overall": 6.9,
    "previous": 5.7,
    "breakdown": {
      "novelty_originality": {"score": 1.0, "max": 2.0, "delta": 0.1},
      "technical_correctness": {"score": 1.5, "max": 2.0, "delta": 0.4},
      "evidence_results": {"score": 1.2, "max": 2.0, "delta": 0.4},
      "literature_citations": {"score": 1.2, "max": 1.5, "delta": 0.1},
      "structure_coherence": {"score": 0.8, "max": 1.0, "delta": 0.1},
      "reproducibility_limitations": {"score": 0.8, "max": 1.0, "delta": 0.1},
      "writing_presentation": {"score": 0.4, "max": 0.5, "delta": 0.0}
    },
    "recommendation": "Major Revision",
    "readiness": "Borderline",
    "realistic_ceiling_without_new_subjects_and_real_baseline": "7.3-7.6 (best case 7.8)"
  },
  "resolved_and_verified": [
    "F-01 (E6: real negation.audit on oracle maps; arms agree; shared data-tag encoding disclosed)",
    "F-02 at fake level (E5 reproduces; interpretation matches graph_runner.act; live stack blocked)",
    "F-04", "F-05", "F-06", "F-07 (Prop 1 renamed/scoped, SAFE column removed, replay bound nkD)",
    "F-08 with caveat (E7 is an engine unit test)", "F-09", "F-10 (E8, Table 3 removed)", "F-12",
    "F-13 for verified entries", "F-15", "F-16"
  ],
  "findings": [
    {"id": "F-03", "severity": "High", "status": "partial", "location": "evaluation.tex RQ5, threats; abstract; discussion",
     "evidence": "E9 baseline A6 reads data-tag, the same encoding the mutator writes and the oracle reads; 64/64 guaranteed; one app; authors wrote app, tool, mutators, baseline",
     "correction": "Add an independent XPath-on-roles/visible-text baseline run on a data-tag-stripped/renamed in-memory copy of the fixture; keep 'own re-implementation, not ATUSA' label; keep claims at fixture level",
     "blocked_part": "additional subject apps and real Crawljax+ATUSA baseline need author/orchestrator approval"},
    {"id": "F-11", "severity": "Medium", "status": "partial", "location": "related.tex Table 1",
     "evidence": "MATE NEG/REQ, AXNav REQ still '?'; axe-core NEG '?' though marquee rule is forbidden-element; ZAP AE '?' though ZAP has spiders (see F-21)",
     "correction": "Resolve each '?' from a cited source or leave with reason"},
    {"id": "F-14", "severity": "Medium", "status": "blocked", "location": "system.tex Perception",
     "evidence": "gemini.py docstring says 2.5 Flash; _MODEL='gemini-3.6-flash'",
     "correction": "Use 'a Gemini Flash model'; remove the in-paper note about the disagreement (F-26); Track C resolves the mismatch"},
    {"id": "F-17", "severity": "Low", "status": "partial", "location": "discussion.tex, conclusion.tex; 20 pages",
     "evidence": "Discussion and Conclusion still restate results; page limit unknown", "correction": "Trim restatements; fit venue limit when known"},
    {"id": "F-18", "severity": "Low", "status": "partial", "location": "evaluation.tex Environment and artifact",
     "evidence": "No archive/DOI; docs/report untracked; cited commit 4487574 predates script and JSON", "correction": "See F-24; archive needs author decision"},
    {"id": "F-19", "severity": "Medium", "status": "open", "location": "system.tex line 41",
     "evidence": "Text: checkpointed dictionary holds 'claimed pairs'. state.py ExplorationState has only visited_pairs counter; claim set is in GraphPort/Redis; same section says claim set lives in Redis",
     "correction": "State that the checkpoint holds frontier, seen, order, skips and counters, while the claim set is in the graph store; note this separation explains the E5 resume result"},
    {"id": "F-20", "severity": "Medium", "status": "open", "location": "evaluation.tex RQ5",
     "evidence": "246/75/77/309 pool 64 variants of 6 pages (309 = 6*64-75); 'reproduces ... at scale' overstates; A2/A6 agreement guaranteed by shared encoding",
     "correction": "Report per mutant family; replace 'at scale'; mark counts non-independent; add independent baseline (F-03)"},
    {"id": "F-21", "severity": "Medium", "status": "open", "location": "related.tex Table 1 rows axe-core, ZAP, MATE; paragraph after the table",
     "evidence": "axe 'marquee' rule: '<marquee> elements must not be present' (forbidden-element); ZAP has spiders; sentence 'fixed rules of one polarity each' wrong for axe-core; axe bypass also passes on heading or landmark",
     "correction": "Mark axe NEG and ZAP AE from cited sources (add axe marquee and ZAP spider sources to bib); reword the sentence; note bypass accepts alternatives; keep 'no row combines' scoped to the table"},
    {"id": "F-22", "severity": "Low", "status": "open", "location": "evaluation.tex RQ1 Crash and resume; Table 4; discussion Resuming safely",
     "evidence": "claim-set-only restart never continues only because the seed has one action; 11 positions share one mechanism",
     "correction": "Qualify as fixture-specific; optionally add a two-seed-action variant; do not present 11/11 as statistical"},
    {"id": "F-23", "severity": "Low", "status": "open", "location": "model.tex Prop 1; evaluation.tex RQ1(b)",
     "evidence": "33 = 11*3 uses observed depth 3; configured depth_limit is 10", "correction": "Say D is the observed maximum depth (3)"},
    {"id": "F-24", "severity": "Low", "status": "open", "location": "artifact / audit documents",
     "evidence": "docs/report untracked; no RQ/arm to JSON-key map; LangGraph msgpack warnings; revision-matrix-02 table numbers stale",
     "correction": "Add key map in a README; commit/tag artifact if authors agree; correct matrix table numbers"},
    {"id": "F-25", "severity": "Low", "status": "open", "location": "references.bib; related.tex LLM/VLM agents paragraph",
     "evidence": "Missing pages (Stoat 245-256, WebMate 55-69, Yandrapally 186-197, nl2spec 383-396, NL2LTL 16428-16430); VisionDroid is Trident in arXiv v2; 'grounding as the main obstacle' for WebArena unverified; Sun et al. is static analysis; Noseevich and CREPE pages unverified",
     "correction": "Add pages; note the Trident rename; re-check or soften the grounding attribution; fix the Sun wording"},
    {"id": "F-26", "severity": "Low", "status": "open", "location": "system.tex Perception",
     "evidence": "In-paper note that the configured identifier and the docs disagree reads like a working note", "correction": "Neutral wording; file mismatch with Track C"}
  ],
  "must_not_change": [
    "The exploration graph is CYCLIC; never call it a DAG; never prune revisit/back edges; loop prevention = visited (state_id, action_id) set only",
    "RQ1/RQ3 use FakePerception and a scripted crawler; never present as end-to-end",
    "REPLAY_SAFE_KINDS = {navigate, click, back}; click is replay-safe; keep the residual-risk statement",
    "Only report numbers present in data/experiments.json or reproduced by run_experiments.py; any new experiment must be authorised, stored, and reproduce from the script",
    "Do not edit E1-E9 code/values to improve results; keep E5 negative result and E8 over-merge findings",
    "Keep the disclosures: oracle arms read data-tag; baseline is our own re-implementation, not Crawljax/ATUSA; no browser/Neo4j/Redis; A4 post hoc",
    "Do not invent citations/results/detector scores; do not claim plagiarism-free",
    "Authors remain placeholders; do not modify svproc.cls; do not load amsthm; abstract <=150 words",
    "Keep 'formalise and combine' scoping; do not claim first crawler, novel cyclic graph, novel fingerprint, OWASP A01 detection, NL-policy-driven audit, or solved VLM negation",
    "Do not change anything outside docs/report/"
  ],
  "blocked_by_missing_evidence": [
    {"item": "Additional independent subject apps and real Crawljax+ATUSA baseline (F-03)", "needed": "Author/orchestrator approval and apps"},
    {"item": "End-to-end Playwright to semantic map to audit run", "needed": "Track C vocabulary decision and authorisation"},
    {"item": "Live Neo4j/Redis/durable-checkpointer crash test", "needed": "Infra and authorisation"},
    {"item": "VLM/hybrid per-polarity accuracy", "needed": "API key, wired channel, labelled probe set"},
    {"item": "Gemini model id mismatch (F-14)", "needed": "Track C"},
    {"item": "Archive/DOI (F-18)", "needed": "Author decision"},
    {"item": "Authors, venue, page limit", "needed": "Author decision"},
    {"item": "Similarity corpus; AI-detector results", "needed": "None provided"}
  ],
  "unresolved_questions": [
    "Venue page limit versus 20 pages",
    "Will authors authorise the independent XPath baseline and fixture variants (in-memory only)?",
    "Rename policy subjects or read annotations (Track C)?",
    "Should the E5 resume finding be filed as an issue with Track B?"
  ],
  "previous_iterations": [
    {"iteration": 1, "score": 5.7, "recommendation": "Major Revision"}
  ],
  "iteration_budget": {"threshold": 8.0, "iterations_remaining_after_this": 2,
    "note": "Fix F-19..F-26 and add the independent baseline in iteration 3; 8.0 needs extra subjects and a real baseline, otherwise mark blocked and report honestly"}
}
```

Relevant files, all read-only:
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/sections/system.tex` (F-19 at line 41)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/sections/related.tex` (F-21)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/sections/evaluation.tex` (F-20, F-22)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/springer/references.bib` (F-25)
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/data/experiments.json`
- `/home/kr95/Projects/final-year-project/statescout-ai/docs/report/experiments/run_experiments.py`
- `/home/kr95/Projects/final-year-project/statescout-ai/apps/agent/orchestrator/graph_runner.py`
- `/home/kr95/Projects/final-year-project/statescout-ai/apps/agent/orchestrator/state.py`

Sources checked:
- [ATUSA, IEEE TSE 2012 (full text)](https://people.ece.ubc.ca/amesbah/resources/papers/tse11.pdf)
- [Sun et al., USENIX Security 2011](https://www.usenix.org/conference/usenix-security-11/static-detection-access-control-vulnerabilities-web-applications)
- [Doupé et al., USENIX Security 2012](https://www.usenix.org/conference/usenixsecurity12/technical-sessions/presentation/doupe)
- [Kea, ASE 2024](https://conf.researchr.org/details/ase-2024/ase-2024-research/5/General-and-Practical-Property-based-Testing-for-Android-Apps)
- [BACScan, CCS 2025](http://secsys.fudan.edu.cn/publications/content/2025-12-10-003/)
- [WebTestPilot, arXiv 2602.11724](https://arxiv.org/abs/2602.11724)
- [VisionDroid / Trident, arXiv 2407.03037](https://arxiv.org/abs/2407.03037)
- [AUITestAgent, arXiv 2407.09018](https://arxiv.org/abs/2407.09018)
- [BACFuzz, arXiv 2507.15984](https://arxiv.org/abs/2507.15984)
- [ST-WebAgentBench, arXiv 2410.06703](https://arxiv.org/abs/2410.06703)
- [axe `bypass` rule](https://dequeuniversity.com/rules/axe/4.10/bypass)
- [axe `marquee` rule](https://dequeuniversity.com/rules/axe/4.10/marquee)
- [ZAP passive scan rules](https://www.zaproxy.org/docs/desktop/addons/passive-scan-rules/)
- [ZAP users in contexts](https://www.zaproxy.org/docs/desktop/start/features/users/)
- [WCAG 2.2 Understanding 2.4.1](https://www.w3.org/WAI/WCAG22/Understanding/bypass-blocks.html)
- [AXNav, CHI 2024](https://arxiv.org/pdf/2310.02424)
- [UIGuard, UIST 2023](https://arxiv.org/html/2308.05898v2)
- [DroidAgent, ICST 2024](https://conf.researchr.org/details/icst-2024/icst-2024-papers/19/Intent-Driven-Mobile-GUI-Testing-with-Autonomous-Large-Language-Model-Agents)
- [Stoat, ESEC/FSE 2017](https://pure.ecnu.edu.cn/en/publications/guided-stochastic-model-based-gui-testing-of-android-apps/)
- [APE, ICSE 2019](https://2019.icse-conferences.org/details/icse-2019-Technical-Papers/75/Practical-GUI-Testing-of-Android-Applications-via-Model-Abstraction-and-Refinement)
- [Memon et al., FSE 2000](https://www.cs.umd.edu/~atif/pubs/MemonFSE2000-abstract.html)
- [GUI Ripping, WCRE 2003](https://www.cs.umd.edu/~atif/pubs/MemonWCRE2003-abstract.html)
- [MATE, ICST 2018](https://ieeexplore.ieee.org/document/8367041)