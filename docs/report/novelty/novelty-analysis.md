# StateScout AI: Novelty Analysis

*Prepared by novelty-scout, 2026-09-22. Every citation key refers to
`docs/report/paper/references.bib`; every entry there was located and checked
(title, authors, venue, year) by web search or fetch in this session.*

> **Bottom line.** StateScout's *components* all have prior art. Crawling to a
> state graph dates to Crawljax, DOM invariant oracles to ATUSA, per-role access
> analysis to Sun et al. 2011, and VLM GUI testing to VisionDroid. The defensible
> contribution is the **combination and its formal framing**: a *polarity-typed,
> role-scoped policy oracle* (`S ∩ F` ∪ `R \ S`), evaluated on every state of a
> *cyclic, side-effect-aware* exploration. Absence is judged on deterministic
> DOM+AX evidence, not by a VLM, because VLMs are known to fail at negation.
> Write the paper as "we unify and formalise", not as "we are the first to".

---

## 0. What the code actually does (checked 2026-09-22)

The paper must separate **implemented** from **planned**. Findings from reading
the repository:

| Aspect | Status | Evidence |
| --- | --- | --- |
| Frozen typed interfaces; `Polarity` = `must_exist`/`must_not_exist`; `ClauseType` = `forbidden_present`/`required_absent` | Implemented | `apps/agent/contracts.py` |
| Audit = `S ∩ forbidden` ∪ `required \ S`, over element tags, element names and capabilities, exact match after normalisation (no substring matching) | Implemented | `apps/agent/negation/audit.py` |
| Role scoping: a clause applies when `roles` is empty or contains the run's role | Implemented | `negation/audit.py::_applies` |
| Page or state predicates on clauses | **Not implemented** (known limitation) | `test-apps/broken-admin/README.md`, "Known limitation" |
| Severity per clause | **Not in contract**: `audit.py` hard-codes high for forbidden and medium for required, but `policy.json` carries severities that are ignored | `negation/audit.py::_severity_for` |
| Perception = deterministic DOM + CDP AX correlation (role+name, then name-only when unique, unmatched evidence kept) with keyword rules for tags and capabilities | Implemented | `apps/agent/perception/correlate.py`, `semantic_map.py`, `dom.py` |
| Gemini VLM path that *merges* tags onto the deterministic element list and never adds or removes elements; audit stays deterministic | Partial (code exists; `state_id` placeholder; not wired into the orchestrator) | `apps/agent/perception/gemini.py` module docstring |
| NL policy → `ExpectationSet` parsing | **Planned** (Month 3); `policy.json` is hand-structured | `test-apps/broken-admin/policy.json` "comment" |
| Fine-tuning / benchmark | **Planned** (READMEs only) | `research/finetune/README.md`, `research/benchmark/README.md` |
| Fingerprint = SHA-256 over normalised URL \| DOM \| AX (strips nonces, CSRF, session tokens, hex ids, ≥10-digit timestamps, CDP node ids, `focused`) | Implemented | `apps/agent/graph/fingerprint.py` |
| Cyclic graph: back-edges flagged `is_back_edge`, persisted, never pruned | Implemented | `contracts.py::StateEdge`, `graph/graph_store.py`, `orchestrator/explore.py` |
| `mark_visited` called **before** `crawler.act` (at-most-once per `(state_id, action_id)`) | Implemented | `orchestrator/explore.py` main loop; `graph_runner.py` (parity-tested) |
| Replay restricted by action kind | Implemented, **but** `REPLAY_SAFE_KINDS = {navigate, click, back}`: **click** is replayed too, not only navigation | `orchestrator/state.py:48` |
| Termination proof sketch (bounded enqueues, `max_states` backstop) | Documented | `orchestrator/explore.py` module docstring |
| Ground truth `broken-admin`: 6 states, 4 cycles, 4 planted violations (3 forbidden-present, 1 required-absent), exact-set assertion | Implemented, **but** the ground-truth test runs on `FakePerception` (reads `data-tag` attributes) and a scripted crawler built from `app.json`, and uses the fake's own set algebra, not `negation/audit.py` | `tests/integration/orchestrator/test_ground_truth.py`, `orchestrator/fakes.py::FakePerception` |

**Blocking caveat for any exact-recall claim.** The real deterministic perception
does not read `data-tag`. Its keyword rules produce tags such as `admin`, `debug`
and `delete`, while the policy subjects are `admin-link`, `debug-panel` and
`skip-to-content`. `audit.py` matches exactly, so on the real pages clauses
`e-admin-link`, `e-debug-panel` and `e-skip-link` would not match as written.
`e-delete-user` would still fire through the `delete-user` capability. The
skip-link clause would then *falsely* fire as `required_absent` on every page.
Until the real `PlaywrightCrawler` → `build_semantic_map` → `negation.audit`
pipeline reproduces the 4/4 result, the paper may claim only that "the
orchestration and oracle logic achieve exact recall against a scripted model of
the app". It may not claim this for the end-to-end system.

---

## 1. Related-work matrix

Legend: **✓** stated capability · **~** partial or qualified (see note) · **✗** not
a goal or absent · **?** not confirmed from what was read. Cells for prior work
are based on the abstract or paper text consulted in this session. Spot-check the
**~** and **?** cells before camera-ready.

Columns: **AE** autonomous exploration · **CYC** cyclic state graph kept ·
**POL** NL or declarative policy · **NEG** "must-not-exist" oracle · **REQ**
"required-absent" oracle · **ROLE** role-scoped · **MM** multimodal perception ·
**SAFE** side-effect safety (at-most-once) · **GT** ground-truth benchmark with
exact recall.

| System (key) | AE | CYC | POL | NEG | REQ | ROLE | MM | SAFE | GT | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Crawljax `mesbah2012crawljax` | ✓ | ✓ | ✗ | ~ | ~ | ✗ | ✗ | ✗ | ✗ | State-flow graph; `NotXPathCondition` ("true iff no elements are found") exists as a crawl/invariant condition |
| ATUSA `mesbah2012invariant` | ✓ | ✓ | ~ | ✓ | ✓ | ✗ | ✗ | ✗ | ? | Generic and app-specific DOM invariants as oracles; hand-written Java/XPath, no roles. **Nearest neighbour for the oracle.** |
| GUI Ripping `memon2003ripping` | ✓ | ~ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | GUI forest + event-flow graphs |
| GUI oracles `memon2000oracles` | ✗ | ✗ | ~ | ~ | ~ | ✗ | ✗ | ✗ | ✗ | Expected-state oracle after each action |
| WebMate `dallmeier2013webmate` | ✓ | ? | ✗ | ✗ | ✗ | ~ | ✗ | ✗ | ✗ | Takes credentials; one user; state abstraction |
| Sapienz `mao2016sapienz` | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | Search-based; crash oracle |
| Stoat `su2017stoat` | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | Stochastic FSM model; crash oracle |
| APE `gu2019ape` | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | Model abstraction/refinement |
| DroidBot `li2017droidbot` | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | On-the-fly state transition model |
| Humanoid `li2019humanoid` | ✓ | ~ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | Learned action choice (DroidBot-based) |
| Kea `xiong2024kea` | ✓ | ~ | ✓ | ~ | ~ | ✗ | ✗ | ✗ | ~ | Property description language; functional properties, 124 historical bugs |
| State-aware scanner `doupe2012enemy` | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ~ | ✗ | Infers server state machine; tracks state-changing requests |
| Sun et al. `sun2011static` | ✗ (static) | ~ | ✗ | ~ | ✗ | ✓ | ✗ | n/a | ✗ | Per-role sitemaps, forced-browsing check |
| Li et al. `li2014blackbox` | ✓ | ? | ✗ | ~ | ✗ | ✓ | ✗ | ? | ✗ | Black-box multi-role AC testing |
| Noseevich `noseevich2011detecting` | ✓ | ~ | ✗ | ~ | ✗ | ✓ | ✗ | ? | ✗ | Use-case graph, black-box |
| MACE `monshizadeh2014mace` | ✗ (static) | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | n/a | ✗ | Authorization-context consistency |
| BACScan `liu2025bacscan` | ✓ | ✓ | ✗ | ~ | ✗ | ✓ | ✗ | ✗ | ✓ | Replays modification requests deliberately; 44-vuln ground truth; 89 vulns found |
| BACFuzz `dharmaadi2025bacfuzz` | ✓ | ? | ✗ | ~ | ✗ | ✓ | ✗ | ✗ | ? | SQL-level oracle; preprint |
| GPTDroid `liu2024gptdroid` | ✓ | ~ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | LLM Q&A exploration; functionality memory |
| DroidAgent `yoon2024droidagent` | ✓ | ~ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | Intent-driven LLM agent |
| AutoDroid `wen2024autodroid` | ~ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ~ | Task automation (not testing); UTG from exploration |
| VisionDroid `liu2024visiondroid` | ✓ | ~ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ~ | MLLM non-crash functional-bug detection |
| AXNav `taeb2024axnav` | ✗ | ✗ | ✓ | ~ | ~ | ✗ | ✓ | ✗ | ✗ | Replays NL accessibility test instructions |
| AUITestAgent `hu2024auitestagent` | ✗ | ✗ | ✓ | ~ | ~ | ✗ | ✓ | ✗ | ~ | NL requirements → interaction + verification |
| WebTestPilot `teoh2026webtestpilot` | ✗ | ✗ | ✓ | ? | ? | ✗ | ✓ | ✗ | ~ | NL spec → symbolised pre/post-condition oracles; preprint |
| MATE `eler2018mate` | ✓ | ? | ✗ | ~ | ✓ | ✗ | ✗ | ✗ | ✗ | Fixed accessibility checks during exploration |
| UIGuard `chen2023uiguard` | ✗ | ✗ | ~ | ✓ | ✗ | ✗ | ✓ | n/a | ~ | Fixed dark-pattern taxonomy → presence detection |
| WebArena `zhou2024webarena` | ✗ | n/a | ✗ | ✗ | ✗ | ✗ | ~ | ✗ | ~ | Agent benchmark; functional-correctness grading |
| Mind2Web `deng2023mind2web` | ✗ | n/a | ✗ | ✗ | ✗ | ✗ | ~ | ✗ | ~ | Agent dataset |
| SeeAct `zheng2024seeact` | ✗ | n/a | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ~ | Shows grounding (HTML+vision) is the bottleneck |
| OSWorld `xie2024osworld` | ✗ | n/a | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ~ | Execution-based task evaluation |
| ST-WebAgentBench `levy2026stwebagentbench` | ✗ | n/a | ✓ | ~ | ~ | ✗ | ~ | ~ | ✓ | Policies constrain the **agent**, not audit the **app** |
| **StateScout (as built)** | ✓ | ✓ | ~ | ✓ | ✓ | ✓ | ~ | ✓* | ~ | *Click is replay-safe; GT harness runs on fakes |

**How to read the matrix.** No single row has ✓ across NEG, REQ, ROLE, CYC and
AE. The rows closest to StateScout are **ATUSA** (NEG/REQ/AE/CYC, no roles, no
semantic abstraction) and **BACScan** (ROLE/AE/GT, but a request-level oracle
rather than a UI-surface oracle). The gap sits in their intersection.

---

## 2. Novelty claims that survive

### C1: A polarity-typed policy oracle with set-algebraic semantics over explored UI states

- **Claim.** StateScout defines UI policy conformance as two distinct set
  operations over a semantic UI abstraction `S` of each explored state:
  `forbidden_present = S ∩ F` and `required_absent = R \ S`. Their union is the
  per-state verdict. Each violation is tagged with the operation that produced it.
  Absence is a first-class violation type, not an afterthought.
- **Nearest prior work.** ATUSA invariants `mesbah2012invariant`, which can check
  both presence and absence of DOM patterns on every crawled state (Crawljax's
  `NotXPathCondition` expresses "no element matches"). Also accessibility checkers
  (`eler2018mate`), which flag missing required attributes, and Kea's property
  language `xiong2024kea`.
- **Concrete delta.** (a) In StateScout, polarity is part of the *policy schema*
  (`Polarity`, `ClauseType`), not an ad-hoc predicate the tester writes in code.
  (b) Clauses range over a *semantic* vocabulary (role, accessible name, tag,
  capability), not raw XPath, so one clause is portable across pages and
  markup. (c) Violations carry their clause type, which the report consumes.
  (d) The formal statement allows an argument that an intersection-only engine
  cannot express FR-19. The planted V-04 exists to test exactly that.
- **Evidence.** `apps/agent/contracts.py` (`Polarity`, `ClauseType`,
  `ExpectationSet`, decision 6); `apps/agent/negation/audit.py`;
  `test-apps/broken-admin/violations.json` (V-04).
- **Honest caveat.** Expressively this adds *nothing* over ATUSA: a skilled user
  can write both kinds of invariant there. The contribution is the formalisation,
  the typed schema and the semantic abstraction. Matching is exact-string over
  keyword-derived tags, so the abstraction is only as good as the tagger (see
  §0). **Write "we formalise and type" and never "we are the first to detect
  missing elements".**

### C2: Role-scoped auditing of the *UI surface*, complementary to request-level access-control testing

- **Claim.** StateScout checks, per role, whether the *rendered, reachable UI*
  exposes elements or capabilities a declarative policy forbids for that role, or
  omits ones it requires. The check applies even when the backend correctly
  rejects the underlying request (V-01).
- **Nearest prior work.** Sun et al. `sun2011static` (per-role sitemaps, forced
  browsing), Li et al. `li2014blackbox` (black-box, multi-role), Noseevich &
  Petukhov `noseevich2011detecting`, MACE `monshizadeh2014mace`, and BACScan
  `liu2025bacscan` (black-box, feedback-driven oracle, CVE-producing).
- **Concrete delta.** These tools decide *whether the server enforces
  authorization*: they compare responses or replay requests under another
  identity. StateScout decides *whether the UI shown to a role conforms to an
  explicit policy*. The oracle is the user-visible surface, the policy is
  declared rather than inferred from role differences, and it includes a
  required-absent half, which BAC tools do not have.
- **Evidence.** `negation/audit.py::_applies`; `contracts.py` decision 5 (one role
  per run); `test-apps/broken-admin/policy.json` (guest-scoped clauses);
  `violations.json` V-01 "why".
- **Honest caveat.** UI exposure is **not** an authorization vulnerability in the
  OWASP A01 sense (`owasp2021a01`). A security reviewer will say that hiding a
  button is not access control. Frame C2 as *policy conformance, information
  exposure and least-privilege UI*, and state explicitly that StateScout does
  not test server-side enforcement. There is no cross-role differential yet
  (decision 5 defers it to reporting). Clauses cannot be scoped by page or state
  predicate, which blocks realistic policies such as "every signed-in page offers
  logout".

### C3: Negation-safe division of labour between deterministic evidence and the VLM

- **Claim.** Existence and absence of elements are decided only from
  deterministic DOM + accessibility-tree evidence. A VLM may *annotate* elements
  already found (tags, capabilities) but may never add or remove one. The audit
  itself is model-free. This is a design response to documented VLM negation
  failure.
- **Nearest prior work.** VisionDroid `liu2024visiondroid` (MLLM decides bugs from
  screenshots), SeeAct `zheng2024seeact` (vision plus HTML grounding for
  *acting*), AXNav `taeb2024axnav`, UIGuard `chen2023uiguard` (CV plus pattern
  matching for presence of dark patterns), AUITestAgent `hu2024auitestagent`.
  The motivating evidence is `alhamoud2025negation` (VLMs near chance on negated
  queries), with `yuksekgonul2023aro` and `ma2023crepe` on compositional weakness.
- **Concrete delta.** Prior MLLM testers let the model issue the verdict. SeeAct
  grounds *actions* in HTML but not *absence verdicts*. StateScout assigns
  absence judgements, the case the negation literature says models get wrong,
  to a component that cannot hallucinate, and gives the VLM a narrower job.
- **Evidence.** `apps/agent/perception/gemini.py` (module docstring "Why merge
  instead of trust the VLM outright"); `perception/correlate.py` (unmatched and
  DOM-only evidence preserved, no forced merges); `contracts.py` decision 7.
- **Honest caveat.** This is a **design claim with no empirical support yet**. The
  Gemini path is partial and not wired in, and no experiment compares VLM-only,
  deterministic and hybrid absence judgements (see RQ2). It also concedes that
  elements with no DOM/AX footprint (canvas-rendered UI) are invisible to the
  existence check. The negation papers study CLIP-style retrieval and MCQ on
  natural images, not UI screenshots, so cite them as *motivation*, not as proof
  that Gemini fails on UIs.

### C4 (systems contribution): Side-effect-aware cyclic exploration with at-most-once action semantics

- **Claim.** The exploration graph is kept cyclic (back-edges recorded, never
  pruned). Loop prevention is only a `(state_id, action_id)` visited set. That
  pair is *claimed before* the action executes, which gives at-most-once
  semantics against a non-idempotent application under test across crash and
  resume. Path replay is restricted to a whitelist of action kinds, and
  candidates behind form fills or submits are reported as skipped, not re-fired.
- **Nearest prior work.** Crawljax `mesbah2012crawljax` (state-flow graph with
  cycles; backtracks by reload and replay), Doupé et al. `doupe2012enemy`
  (state-aware scanning that explicitly models state-changing requests),
  WebMate `dallmeier2013webmate`, DroidBot/Stoat/APE (cyclic models).
- **Concrete delta.** Prior crawlers treat state changes as something to *model*
  (Doupé) or ignore. StateScout makes a *delivery-semantics guarantee* (at most
  once per pair) and ties it to checkpoint and resume. It also reports coverage
  loss from unreplayable paths instead of hiding it.
- **Evidence.** `orchestrator/explore.py` (mark before act; termination argument;
  "Replay conflicts with at-most-once"); `orchestrator/state.py`
  (`REPLAY_SAFE_KINDS`, `replayable`); `contracts.py` decision 3;
  `tests/integration/graph/test_live_crawl.py` (back-edges persisted, zero
  duplicate pairs on Neo4j).
- **Honest caveat.** This is engineering rigour, not a research advance. Present
  it in the system-design section, not as a headline contribution. The guarantee
  is weaker than the prose suggests: **`click` is replay-safe**, so a click that
  triggers a destructive action on the path to a state *is* re-fired during BFS
  replay. At-most-once holds per claimed pair, not per effect. Either narrow
  `REPLAY_SAFE_KINDS` or state this precisely in the paper. "Only navigation is
  replayed" is currently **false**.

### C5 (evaluation artefact, not a novelty): Polarity-complete ground truth scored for exact recall and zero false positives

- **Claim.** A fixture app whose defects are fully enumerated, including an
  *absence*, with cycles that punish back-edge pruning. It is scored for exact
  set equality (no misses, no extras) and doubles as a parity oracle between two
  orchestrator implementations.
- **Nearest prior work.** BACScan's validated ground-truth set; Themis (used by
  DroidAgent); WebArena and OSWorld execution-based grading; Kea's historical-bug
  corpus.
- **Delta.** Small. The distinguishing feature is that polarity coverage is
  deliberate: V-04 exists to exercise `required \ S`.
- **Caveat.** Six static pages is a toy, and today it runs against
  `FakePerception` (see §0). Report it as a *correctness harness*, not a
  benchmark.

---

## 3. Claims that do not survive (keep them out of the paper)

| Tempting claim | Why it fails | Refuting work |
| --- | --- | --- |
| "First autonomous crawler that infers a state graph of a web app" | Crawljax (2012), WebMate, GUI Ripping (2003) | `mesbah2012crawljax`, `dallmeier2013webmate`, `memon2003ripping` |
| "Keeping the graph cyclic is novel" | State-flow graphs, event-flow graphs and UTGs are cyclic by construction | `mesbah2012crawljax`, `li2017droidbot`, `su2017stoat` |
| "First to detect a *missing* required element" | ATUSA invariants and accessibility checkers already do this | `mesbah2012invariant`, `eler2018mate` |
| "First to detect forbidden UI elements" | Dark-pattern detection flags forbidden UI; ATUSA error-message invariants | `chen2023uiguard`, `mesbah2012invariant` |
| "Detects broken access control / OWASP A01 vulnerabilities" | StateScout never tests server enforcement. V-01 is by design a case where the backend is *correct* | `owasp2021a01`, `liu2025bacscan`, `li2014blackbox` |
| "Natural-language policies drive the audit" | Not implemented (policy is hand-structured JSON). NL→spec is also prior art | `cosler2023nl2spec`, `fuggitti2023nl2ltl`, `hu2024auitestagent`, `teoh2026webtestpilot` |
| "First VLM/MLLM-based GUI tester" | VisionDroid, AXNav, AUITestAgent, SeeAct | `liu2024visiondroid`, `taeb2024axnav`, `hu2024auitestagent`, `zheng2024seeact` |
| "StateScout solves VLM negation" | It *avoids* the problem by routing absence to deterministic evidence | `alhamoud2025negation` |
| "Novel state fingerprinting / normalisation" | Near-duplicate detection is well studied; token stripping is standard practice | `yandrapally2020nearduplicate` |
| "Novel loop prevention" | A visited set is textbook BFS | n/a |
| "Achieves 100% recall with zero false positives" | Only shown with `FakePerception` plus a scripted crawler. The real perception tagger would currently miss 3/4 subjects and raise a false `required_absent` (§0) | repository evidence |
| "Policy compliance for web agents" (conflating with ST-WebAgentBench) | Those policies constrain the *agent's* behaviour. StateScout audits the *application* | `levy2026stwebagentbench` |
| "Only navigation actions are replayed" | `REPLAY_SAFE_KINDS` includes `click` | `orchestrator/state.py:48` |

---

## 4. Research questions

- **RQ1 (Oracle correctness).** Does the polarity-typed audit reach exact recall
  and zero false positives on apps with planted `forbidden_present` *and*
  `required_absent` violations, **end to end** (Playwright crawler → deterministic
  perception → `negation.audit`)? How does it degrade as violations are injected
  or removed?
- **RQ2 (Negation-safe perception).** For presence and absence judgements, how
  accurate are (a) deterministic DOM+AX, (b) VLM-only (screenshot → "is X
  present?"), and (c) the hybrid? Is the VLM error concentrated on the
  *absence* polarity, as `alhamoud2025negation` predicts for natural images?
- **RQ3 (Exploration cost under side-effect safety).** How much coverage does
  at-most-once with kind-restricted replay cost (skipped-unreplayable fraction,
  replay steps per visited pair)? How does normalised fingerprinting affect the
  state count relative to a Crawljax baseline on the same apps?
- **RQ4 (Policy expressiveness).** What fraction of realistic UI-policy sentences
  can be expressed under role-only scoping, and what fraction needs page or
  state predicates? What does adding a scope predicate cost in false positives
  avoided?

## 5. Evaluation design

**Subjects.**
1. `broken-admin` (existing) plus **mutants**: automatically remove each planted
   violation, add new ones (both polarities), and apply cosmetic perturbations
   (reorder, rename ids, inject nonces). Perturbations must *not* change the
   verdict, which tests the fingerprint and the tagger.
2. Two or three open-source, multi-role web apps with a self-hosted instance.
   Choose apps where admin versus guest UIs differ. Label per-role ground truth by
   hand, with two annotators and reported agreement.
3. A **perception probe set** for RQ2: pairs of near-identical pages differing
   only in one element's presence. Include hard cases: a styled `<div>` with no
   role, `display:none`, `aria-hidden`, off-screen, disabled, icon-only
   controls. Balance present and absent 50/50.

**Baselines.**
- *Crawljax + hand-written ATUSA-style invariants* encoding the same policy. This
  is the strongest baseline for C1: compare expressiveness (lines of spec per
  clause), portability across pages, and recall/precision.
- *VLM-only judge* (same Gemini model, screenshot + clause → verdict) for RQ2.
- *Role-differential diff* (crawl as guest and as admin, flag admin-only
  elements visible to guest) as a naïve policy-free baseline for C2.
- Do **not** benchmark against BAC scanners on their own metric. They answer a
  different question. At most, report overlap on shared subjects.

**Metrics.** Per-polarity precision, recall and F1 (report `forbidden_present`
and `required_absent` separately, never pooled). Exact-set match rate on
mutants. States, edges, back-edges, replay steps, skipped pairs, wall time. VLM
calls and cost. For RQ4: clause coverage percentage on a collected policy corpus.
Write the sentences *before* looking at the apps to avoid tailoring.

**Threats to validity.** Small subject count. Planted-defect bias (the authors
wrote both the fixture and the tool). Keyword tagger overfit to the fixture
vocabulary. Single role per run. VLM nondeterminism: fix temperature, report
across ≥3 seeds.

**Pre-requisites before any number goes in the paper.**
1. Wire `build_semantic_map` and `negation.audit` into the ground-truth test (or a
   sibling test) with the real crawler.
2. Reconcile the subject vocabulary: either read `data-tag` in `dom.py`, or rename
   policy subjects to the tagger's vocabulary. This is a Track C decision.
3. Decide whether `click` stays replay-safe (Track B), and document the choice.

---

## 6. Suggested contribution paragraph (draft)

> We present StateScout, an autonomous auditor that checks a web application's
> user interface against a role-scoped declarative policy. Our contributions are:
> (i) a polarity-typed policy oracle that treats forbidden-present (`S ∩ F`) and
> required-absent (`R \ S`) as distinct set operations over a semantic UI
> abstraction, evaluated on every state of the exploration; (ii) a
> negation-safe perception design in which element existence and absence are
> decided from deterministic DOM and accessibility-tree evidence, and a
> vision-language model only annotates, motivated by documented negation failures
> in VLMs; (iii) a side-effect-aware exploration loop that keeps the state graph
> cyclic and gives at-most-once execution of each (state, action) pair; and (iv) a
> polarity-complete ground-truth fixture scored for exact recall. Unlike
> access-control scanners, StateScout audits what each role *sees* in the UI,
> not whether the server enforces authorization. The two are complementary.
