# Dynamic-state literature survey for StateScout AI

Date: 2026-10-15. Purpose: ground the response to the review panel (fails on dynamic sites; count clicks per API endpoint; use a probabilistic graph model).

Verification key. "Opened" means I read the paper text or abstract page. "Search-verified" means bibliographic details were returned by search results but I did not read the paper. "Unverified" means a detail I could not confirm. The search was not exhaustive; "no prior work found" means none surfaced, not that none exists.

Revision note (2026-10-15): this file was drafted by an interrupted agent and then re-checked entry by entry against search results and, where the PDF was readable, the paper text (Roest 2010, Yandrapally 2020, WebExplor 2021). Corrections are applied inline; the table at the end records the status of every citation. Two works found during the re-check were added (4.6, 4.7) because they weaken the novelty claim in Positioning.

Our baseline (from `docs/handoff/PROJECT_STATE.md`): `state_id` = sha256(normalised URL | DOM | AX tree); normalisation strips nonces, CSRF values, session ids, hex ids, long digit runs; the visited set of `(state_id, action_id)` is the only loop control; `max_states` is the backstop; replay needs an exact fingerprint match; there is no network capture and edges carry no counts.

---

## 1. State abstraction and equivalence in web/GUI crawling

**1.1 Mesbah, van Deursen, Lenselink. "Crawling Ajax-based web applications through dynamic analysis of user interface state changes." ACM Transactions on the Web 6(1), article 3, 2012.** DOI 10.1145/2109205.2109208. https://people.ece.ubc.ca/amesbah/resources/papers/tweb-final.pdf (search-verified; extends Mesbah, Bozdag, van Deursen, "Crawling AJAX by Inferring User Interface State Changes", ICWE 2008).
- Contribution: Crawljax. It fires events on candidate elements, compares the DOM before and after, and builds a state-flow graph. The graph is cyclic.
- Relation: this is our design in outline. A state is a DOM snapshot, edges are events, and the graph is not a DAG.
- Borrow: the state-flow-graph model and the candidate-clickable heuristics. Avoid: raw DOM equality or a single global distance as the only identity. Crawljax itself moved away from that (1.2).
- Detail on the original Levenshtein comparison comes from a secondary description and is unverified.

**1.2 Roest, Mesbah, van Deursen. "Regression Testing Ajax Applications: Coping with Dynamism." ICST 2010, pp. 127-136.** https://people.ece.ubc.ca/amesbah/resources/papers/icst10.pdf (opened; pipelined comparators, preconditions and the date-time and `class` examples confirmed in the text).
- Contribution: pipelined oracle comparators plus generated DOM templates to cope with non-deterministic content in Ajax UIs. Comparators can carry preconditions. The paper's examples include date-time text and attribute differences such as `class`.
- Relation: the closest ancestor of "volatility-masked state classes". Its masks are authored by hand or built from template generators, not learned from repeated visits.
- Borrow: pipelined normalisers, preconditions (a mask applies only where it is valid), and masking over deleting content wholesale. Avoid: a manually curated mask list per target app.

**1.3 Yandrapally, Stocco, Mesbah. "Near-Duplicate Detection in Web App Model Inference." ICSE 2020, pp. 186-197.** DOI 10.1145/3377811.3380416. https://people.ece.ubc.ca/astocco/pubs/2020-Yandrapally-ICSE2020.pdf (opened; abstract confirmed; page range from DBLP via search).
- Contribution: the first study of near-duplicate detection inside model inference. It classified a random sample of state pairs, drawn from 493k pairs of pages from over 6,000 websites, as clone, near-duplicate or distinct, and evaluated 10 techniques with computed thresholds on nine open-source apps. Finding: even with the best thresholds, no algorithm detects all functional near-duplicates without losing coverage.
- Relation: direct evidence for the panel's point. Our exact-hash identity is the strict extreme, and a single similarity threshold is the loose extreme. Both fail.
- Borrow: their labelled corpus idea and evaluation protocol (clone / near-duplicate / distinct) for our own state-class accuracy test. Avoid: a global threshold.

**1.4 Yandrapally, Mesbah. "Fragment-Based Test Generation For Web Apps." IEEE TSE (accepted; arXiv 2110.14043, 2021, v2 2022).** https://arxiv.org/abs/2110.14043 (arXiv abstract confirmed by search; the DOI 10.1109/TSE.2022.3171295 is the one the arXiv listing points to; also a journal-first talk at ICSE 2023).
- Contribution: FragGen splits a page into fragments and compares fragments, removing the whole-page threshold. The abstract reports 62% more precision and 70% more recall in inferred models on average, and 123% more near-duplicates detected than whole-page techniques (figures from the abstract; I did not read the full paper) and uses fragments to guide exploration and oracles.
- Relation: a structural, template-like alternative to hashing the whole bundle. It is still deterministic and per-pair; it does not learn which fragments are volatile.
- Borrow: fragment-level identity, so a changing feed region does not rename the whole state. Avoid: re-implementing their fragment clustering. We can use AX-landmark regions instead.

**1.5 Le Breton, Maronnaud, Hallé. "Automated Exploration and Analysis of Ajax Web Applications with WebMole." WWW 2013 Companion Volume (Demos track), pp. 245-248.** https://archives.iw3c2.org/www2013/companion/p245.pdf (authors and pages corrected from the draft, which had the third author missing; confirmed by search of the proceedings page and DBLP).
- Contribution: browser-based exhaustive exploration of Ajax apps, including JS-triggered links and state changes without a reload, with user-defined oracles that both bound exploration and test conditions on every page.
- Relation: oracles on every visited state, as in our policy audit. Its state identity is DOM content rather than URL (from a search-result description).
- Borrow: oracle-as-scope as a precedent for policy-driven pruning. Avoid: nothing specific.

**1.6 Pellegrino, Tschürtz, Bodden, Rossow. "jÄk: Using Dynamic Analysis to Crawl and Test Modern Web Applications." RAID 2015, LNCS 9404, pp. 295-316.** https://publications.cispa.saarland/538 (search-verified).
- Contribution: hooks JavaScript APIs to observe event registrations, network calls and generated URLs, then builds a navigation graph. Reported 86% more surface than four scanners on 13 apps.
- Relation: SPA crawling plus network observation, which is pillar (b). It targets security scanning, not policy violation, and has no state-volatility model.
- Borrow: instrument at the page level (Playwright `request`/`response`) so handlers and requests are attributed to the action that fired them.

---

## 2. Learned probabilistic models, and exploration policies

**2.1 Whittaker, Thomason. "A Markov chain model for statistical software testing." IEEE TSE 20(10), October 1994, starting p. 812.** (title, volume, issue and start page confirmed from the paper header found by search; end page not confirmed.)
- Contribution: Markov-chain usage models. States are use states, transitions carry probabilities, a second chain is built from test results, and an analytical comparison of the two chains gives a stopping criterion (that it is "information-theoretic" is not confirmed by what I read).
- Relation: a classical precedent for transition probabilities on a state graph. Probabilities here are specified or estimated, and the model is not learned over a volatile state space.
- Borrow: using a distance between the prior and the observed chain as an evidence-of-saturation signal. Avoid: using it as the termination rule, since termination stays with the visited set.

**2.2 Carrasco, Oncina. "Learning stochastic regular grammars by means of a state merging method." ICGI 1994, LNAI 862, DOI 10.1007/3-540-58473-0_144 [pages unverified: sources give 139-152 and 130-138]; and "Learning deterministic regular grammars from stochastic samples in polynomial time." RAIRO-ITA 33(1), 1999, pp. 1-19.** https://www.rairo-ita.org/10.1051/ita:1999102 (both search-verified; the draft's page range for 1994 could not be confirmed and is not relied on).
- Contribution: ALERGIA-style learning of deterministic stochastic automata by merging compatible states, with a statistical (Hoeffding-type) compatibility test. The 1999 paper reports running time linear in sample size. (The name ALERGIA is tied to the Carrasco-Oncina algorithm by Mao et al., 2.3.)
- Relation: this is the principled way to merge fingerprints. Two prefix-tree states merge when their outgoing action distributions are statistically indistinguishable. That is a learned equivalence from behaviour, not from DOM similarity.
- Borrow: the compatibility test as a state-class merge criterion, applied to the successor-class distribution and the endpoint-call signature of each action. Avoid: merging driven only by successor statistics, since two states with the same successors can differ in policy-relevant content (a Delete button). Policy-relevant elements must be a hard split signal.

**2.3 Mao, Chen, Jaeger, Nielsen, Larsen, Nielsen. "Learning deterministic probabilistic automata from a model checking perspective." Machine Learning 105(2), 2016, pp. 255-299.** DOI 10.1007/s10994-016-5565-9. https://mlanthology.org/mlj/2016/mao2016mlj-learning (search-verified). Related: "Learning Markov Decision Processes for Model Checking," QFM 2012, EPTCS 103, pp. 49-63, arXiv 1212.3873 (search-verified, same six authors).
- Contribution: extends Alergia to reactive and timed systems with convergence results, and to MDPs with nondeterministic and probabilistic transitions.
- Relation: if the crawler chooses actions (nondeterminism) and the app responds stochastically, the right model is an MDP, not a Markov chain.
- Borrow: the MDP split of "our choice" versus "environment response", and the convergence arguments as a template for our claims. Avoid: model-checking machinery, which is out of scope.

**2.4 Stolcke, Omohundro. "Hidden Markov Model Induction by Bayesian Model Merging." NIPS 5 (1992 conference; some listings say 1993), pp. 11-18.** https://papers.neurips.cc/paper_files/paper/1992/hash/5c04925674920eb58467fb52ce4ef728-Abstract.html (search-verified). Companion: "Inducing Probabilistic Grammars by Bayesian Model Merging," ICGI 1994, arXiv cmp-lg/9409010 (search-verified).
- Contribution: start from the most specific model, merge states greedily, and use the Bayesian posterior to choose merges and the stopping point.
- Relation: a Bayesian alternative to the Alergia test, with a built-in Occam preference. It gives posterior mass to "these two fingerprints are the same class", which is exactly the replay-tolerance quantity we want.
- Borrow: the posterior over merges as a confidence on state-class membership. Avoid: full HMM induction; our states are observable, so we only need to merge, not to infer hidden structure.

**2.5 Su, Meng, Chen, Wu, Yang, Yao, Pu, Liu, Su. "Guided, stochastic model-based GUI testing of Android apps" (Stoat). ESEC/FSE 2017, pp. 245-256.** DOI 10.1145/3106237.3106298. https://pure.ecnu.edu.cn/en/publications/guided-stochastic-model-based-gui-testing-of-android-apps/ (search-verified, abstract level).
- Contribution: builds a stochastic model of GUI interactions with dynamic and static analysis and a weighted UI exploration strategy, then refines the model with Gibbs sampling to generate tests. The paper reports 17-31% more code coverage in the model-building phase than other modelling tools (abstract figures).
- Relation: transition probabilities on a GUI graph, used for test generation. Its objective is crash and coverage, not policy violation, and it is Android only.
- Borrow: probabilities as weights over the frontier. Avoid: Gibbs resampling of the model, which is too heavy for our need and not tied to a termination guarantee.

**2.6 Zheng, Liu, Xie, Liu, Ma, Hao, Liu. "Automatic Web Testing Using Curiosity-Driven Reinforcement Learning" (WebExplor). ICSE 2021, pp. 423-435.** DOI 10.1109/ICSE43902.2021.00048. https://arxiv.org/abs/2103.06018 (opened full text).
- Contribution: Q-learning with a count-based curiosity reward (MBIE-EB form) over a transition count table N(s,a,s'), plus a DFA that records visited states and transitions and is used to steer back to promising states. States are abstracted by the HTML tag sequence with gestalt pattern matching above a similarity threshold, plus a check on form elements.
- Relation: this already covers part of (b) and (c), namely per-transition counts, a count-based exploration bonus and an automaton-guided frontier on web apps. It also uses a thresholded tag-sequence similarity, which is the weakness 1.3 documents. The counts are per DOM transition, not per backend endpoint.
- Borrow: the count-bonus form (a UCB-like term that decays with visits) for frontier priority, and the idea of replaying along the automaton. Avoid: Q-learning, which has no termination guarantee, and the fixed similarity threshold.
- Also seen but not read: Pan, Huang, Wang, Zhang, Li. "Reinforcement Learning Based Curiosity-Driven Testing of Android Applications" (Q-testing). ISSTA 2020. https://conf.researchr.org/details/issta-2020/issta-2020-papers/40/Reinforcement-Learning-Based-Curiosity-Driven-Testing-of-Android-Applications (search-verified). It uses a trained neural state comparator to decide state novelty at "functional scenario" granularity, a learned (not hash-based) notion of state equivalence.

**2.7 Bandit foundations.** Auer, Cesa-Bianchi, Fischer. "Finite-time Analysis of the Multiarmed Bandit Problem." Machine Learning 47(2-3):235-256, 2002 (UCB1; DOI 10.1023/A:1013689704352; search-verified). Chapelle, Li. "An Empirical Evaluation of Thompson Sampling." NIPS 24, 2011, pp. 2249-2257 (search-verified; https://papers.nips.cc/paper/2011/hash/e53a0a2978c28872a4505bdb51db06dc-Abstract.html).
- Contribution: UCB1 gives regret-bounded exploration from upper confidence bounds. Thompson sampling is simple and empirically competitive.
- Relation: they give a defensible, minimal frontier priority. Beta posteriors per action (Thompson) double as the posteriors we want for "this transition is stable".
- Borrow: Beta-Bernoulli posteriors on (a) "action leads to the same successor class" and (b) "action fires endpoint E". Avoid: expecting regret bounds to transfer; our arms are non-stationary and non-independent, so treat bandits as a heuristic ordering only.

---

## 3. Network-aware testing and crawling

**3.1 jÄk** (see 1.6): observation of network events from page-level hooks.

**3.2 Atlidakis, Godefroid, Polishchuk. "RESTler: Stateful REST API Fuzzing." ICSE 2019.** https://2019.icse-conferences.org/details/icse-2019-Technical-Papers/6/REST-ler-Stateful-REST-API-Fuzzing (search-verified; the ICSE title is "RESTler", without the hyphen. The arXiv preprint 1806.09739 is titled "REST-ler: Automatic Intelligent REST API Fuzzing", a different title for the same work).
- Contribution: infers producer/consumer dependencies between requests from an API specification and learns from responses which sequences are refused.
- Relation: it starts from a Swagger spec, whereas we have only a browser. It shows how endpoints become typed vocabulary for stateful exploration.
- Borrow: treat endpoint calls as a typed alphabet with dependencies. Avoid: active request mutation or fuzzing, which is unsafe against audited apps and out of scope.

**3.3 Suter, Wittern. "Inferring web API descriptions from usage data." 3rd IEEE Workshop on Hot Topics in Web Systems and Technologies (HotWeb), 2015, pp. 7-12.** [unverified] (Seen only as reference-list entries in other papers, e.g. arXiv 1801.08928, which agree on authors, venue and pages; I found no primary page or full text. An IBM page and patents describe classifier-based identification of fixed versus variable path segments, but an IBM page found labels a similar work with a different title and venue (ICWS 2014), so I cannot say they are this paper.)
- Relation: the endpoint-templating problem (`/users/123` to `/users/{id}`) from observed traffic. Borrow the approach of separating static path segments from variable ones.

**3.4 Decrop, Devroey, Papadakis, Schobbens, Perrouin. "You Can REST Now: Automated REST API Documentation and Testing via LLM-Assisted Request Mutations" (RESTSpecIT), arXiv 2402.05102 (v2, July 2025).** https://arxiv.org/pdf/2402.05102 (authors confirmed by search; v1, February 2024, had a different title, "...Automated Specification Inference and Black-Box Testing of RESTful APIs with Large Language Models". Peer-reviewed venue: not found [unverified]; cite as a preprint).
- Contribution: black-box OpenAPI inference by LLM-driven request mutation.
- Avoid: active probing, for the same reason as 3.2.

**3.5 Practice: traffic2openapi (Go tool).** https://pkg.go.dev/github.com/grokify/traffic2openapi (search-verified; not a paper). Normalises HAR/Playwright/proxy captures into an intermediate form and infers OpenAPI.
- Borrow: the pipeline shape (capture, normalise path/query/body shape, template). A search-result patent summary notes that purely passive capture is under-approximate; so endpoint sets only grow monotonically, and we should not assume completeness.

Gap: I found no work that attributes backend calls to individual GUI actions and uses those counts as part of the state or edge identity in a GUI crawler. jÄk is the nearest (calls observed per event, for URL discovery). This is a negative search result, not proof of absence.

---

## 4. Volatile-content and flaky-element handling

**4.1 Roest et al. 2010** (see 1.2): the primary academic treatment of masking non-deterministic regions in a state comparison.

**4.2 Luo, Hariri, Eloussi, Marinov. "An empirical analysis of flaky tests." ESEC/FSE 2014 (DOI 10.1145/2635868.2635920; page range 643-653 [unverified], not shown in the results I read).** (search-verified.) 201 commits fixing flaky tests in 51 projects. Relation: taxonomy of non-determinism sources (async wait, concurrency, time and the like). Borrow: use the categories to seed volatility features (time, ordering, async). Avoid: assuming the unit-test setting transfers directly.

**4.3 Romano, Song, Grandhi, Yang, Wang. "An Empirical Analysis of UI-based Flaky Tests." ICSE 2021, pp. 1585-1597.** DOI 10.1109/ICSE43902.2021.00141. https://arxiv.org/pdf/2103.02669 (search-verified). 235 flaky UI tests from 62 web and Android projects; root causes, trigger strategies and fixes. Relation: confirms async-wait and layout/timing as dominant UI causes, which matches our `networkidle`-with-5s-timeout weakness. Borrow: its root-cause taxonomy for deciding what to wait for versus what to mask.

**4.4 Corazza, Di Martino, Peron, Starace. "Web Application Testing: Using Tree Kernels to Detect Near-duplicate States in Automated Model Inference." ESEM 2021 (arXiv 2108.13322).** https://www.arxiv.org/pdf/2108.13322 (authors and venue confirmed by search; page range not found; paper not read). Relation: a learned structural similarity (tree kernels) as a replacement for hand thresholds. Borrow: treat as an optional similarity feature; unread, so verify before citing results.

**4.5 Practice (vendor documentation, not research).** Applitools (ignore and layout regions), Percy (ignore regions, animation freezing), LambdaTest SmartUI (`ignoreBoxes` / `selectBoxes` by XPath; newer SDK docs use `ignoreDOM` / `selectDOM`, so check the version), Argos (ignoring a specific change, and automatic ignoring of recurring flaky changes by occurrence count). Seen in documentation search results only. The draft's "CSS masking" for Percy was not confirmed and is removed.
- Relation: masks are human-declared regions. A QA guide in the results warns that careless masks create tests that cannot fail. For us the analogue is a mask hiding a policy-relevant element.
- Borrow: "ignore specific changes, not whole regions" (Argos) and animation freezing. Avoid: coordinates or pixel regions as the mask unit, since our state is DOM+AX. Note that Argos's auto-ignore of recurring changes is a small, learned (count-based) volatility filter, in visual regression rather than state identity.

**4.6 Choudhary, Dincturk, von Bochmann, Jourdan, Onut, Ionescu. "Solving Some Modeling Challenges when Testing Rich Internet Applications for Security." ICST 2012.** (Added during re-check; search-verified at abstract level, not read.)
- Contribution (per the abstract): two techniques that improve any DOM-based state equivalence. One finds unimportant dynamic parts of a page by loading and reloading it; the other identifies session parameters so that differences caused by them are ignored.
- Relation: this is prior art for *automatically* detecting volatile page regions and excluding them from state identity. It weakens any claim that learned volatility masking is new in itself. The mechanism is a two-load diff, not a statistical model across many visits.

**4.7 Benjamin, Jourdan, Onut, von Bochmann (IBM). US patent 9,298,850 B2, "System and method for exclusion of irrelevant data from a DOM equivalence." Priority 28 April 2011, granted 29 March 2016.** https://patents.google.com/patent/US9298850B2/en (opened; first 100k characters).
- Contribution: load a page, load it a second time, store the differing portions as a "delta" and exclude it from the DOM used for crawl-time equivalence.
- Relation: same as 4.6. Patent prior art for automatic exclusion of volatile DOM portions. This is not a peer-reviewed source and I did not assess its claim scope beyond claim 1.

---

## Positioning

Scope of the claim: a crawler that (i) learns or explicitly sets volatility masks that define state classes, (ii) keeps per-action backend-endpoint call counts on edges, and (iii) uses transition posteriors for replay tolerance, frontier priority and violation confidence, all under a policy-violation oracle, on a cyclic graph whose termination follows from a visited-set. The search behind this section was bounded (web search and abstract-level reading for most entries). Everything below that says "not found" is a negative search result, not evidence of absence.

### What prior work already covers

- Dynamic-content masking in state comparison, hand-authored: Roest et al. 2010 (comparator pipelines with preconditions, templates). Vendor visual-testing tools (ignore regions).
- Automatic detection of volatile regions by diffing repeated loads of the same page and excluding the delta from state equivalence: Choudhary et al. ICST 2012 (4.6) and the IBM patent US 9,298,850 (4.7). This means "learned volatility masking" is not new as an idea. An earlier draft of this file claimed it was unaddressed; that was wrong.
- Failure of global-threshold identity, and fragment-based or learned alternatives: Yandrapally et al. 2020 and 2022, Q-testing, Corazza et al. 2021.
- Per-transition counts, a count-based curiosity bonus and an automaton-guided frontier on web apps: WebExplor 2021. This covers part of the frontier-priority use of counts.
- Stochastic automata and model learning with statistical or Bayesian merge criteria: Carrasco and Oncina, Stolcke and Omohundro, Mao et al. General, not web-specific.
- Stochastic GUI models and Markov usage models for test generation: Stoat, Whittaker and Thomason.
- Page-level network observation in a crawler: jÄk. Endpoint templating from traffic: Suter and Wittern [unverified], traffic2openapi.

### What I could not find combined (bounded negative result)

1. Volatility estimated statistically across many revisits of the same action path, and folded into state identity together with a merge test. Prior art exists for the two-load diff (4.6, 4.7), so the possible contribution here is narrower: a multi-visit, per-site estimate with an explicit guard that policy-relevant elements are never masked. The guard is the part with no precedent that I saw.
2. Per-action counts keyed by (action, templated endpoint) as part of an edge signature, used to separate "same action, same effect" from "same action, different effect". Counts per transition exist (WebExplor) and network events per event exist (jÄk, for URL discovery). I found no crawler that keys counts by endpoint and uses them as edge identity. I also did not find such a thing in a broader search for per-click backend-call attribution, only DAST tools that catalogue endpoints (not peer-reviewed sources, not cited above).
3. One transition posterior used for three jobs. Frontier priority via counts or bandit terms is covered (WebExplor, bandit literature). Replay tolerance by posterior mass on the observed class instead of exact-hash equality, and violation confidence derived from the stability of the state class in which a finding was observed, were not found. This is the weakest part of the negative result: replay tolerance is a testing-flakiness concern and could exist in test-repair or flaky-test work I did not search.
4. The setting: a policy-violation oracle, a cyclic exploration graph, and a termination guarantee from the finite visited set of `(state_class, action_id)` pairs, with the probabilistic layer only reordering the frontier and refining identity. Related tools optimise coverage or crashes (Stoat, Q-testing, WebExplor) and stop on a budget. I did not find a policy-auditing crawler with this property, but this is a design property of our system more than a research finding, and its proof is still to be written.

### Honest summary

The individual ingredients are established. The defensible novelty is the combination and one safety constraint: (a) endpoint-keyed edge signatures, (b) a single posterior reused across replay, ordering and confidence, and (c) never masking or merging away elements that a policy clause references, with a termination argument that survives mask and merge updates. None of these has been shown to work yet. See the conditions below.

### Conditions for the claim to hold (design risks, not code)

- Termination needs a finite set of classes. Learned masks and merges may change `state_id` mid-run, so merges should be monotone (classes only coarsen, or ids are remapped through a union-find), and `max_states` must stay as the backstop. A split after a pair was marked visited would otherwise reopen it. The graph stays cyclic; no back-edge is pruned.
- Merging on successor statistics alone is unsafe for an auditor. Elements a clause references (forbidden or required subjects) must never be masked or merged away. Show that this preserves recall on `test-apps/` before claiming it.
- Small samples: Alergia-type tests and Bayesian methods need repeated visits to the same state and action. Crawls visit most pairs once, so priors and a small deliberate revisit budget will matter.
- Passive endpoint sets are under-approximate. Report them as observed, not complete.
- Evaluation must be real: the current 4/4 recall holds only against `FakePerception` and a scripted crawler, per the handoff. Any positioning claim needs dynamic test apps (feed, counters, ads, infinite scroll, a modal at a fixed URL) with planted violations, and a baseline that includes exact-hash identity, a Choudhary-style two-load diff, and WebExplor-style counts.

Suggested wording for the paper: "We combine established ingredients (comparator masking and reload-based volatility detection, stochastic-automaton state merging, count-based exploration) in a policy-oriented auditor, with endpoint-keyed edge signatures and a single transition posterior governing replay, ordering and confidence, while termination remains a property of the visited set." Avoid "first".

---

## Verification log

Checked 2026-10-15 by web search; "full text" means I read the PDF text, otherwise the check was at abstract, proceedings-page or bibliographic-record level.

| # | Citation | Status | Note |
| --- | --- | --- | --- |
| 1 | Mesbah, van Deursen, Lenselink, TWEB 6(1) 2012 | confirmed | Added article no. and DOI. |
| 2 | Mesbah, Bozdag, van Deursen, ICWE 2008 | confirmed | Title "Crawling AJAX by Inferring User Interface State Changes" added. |
| 3 | Roest, Mesbah, van Deursen, ICST 2010 | confirmed | Full text checked; pp. 127-136 added. |
| 4 | Yandrapally, Stocco, Mesbah, ICSE 2020 | corrected | Pages 186-197 added; wording of the 493k-pair sample fixed. Abstract and DOI checked in the PDF. |
| 5 | Yandrapally, Mesbah, FragGen (arXiv 2110.14043, TSE) | confirmed | 62% / 70% figures match the abstract. |
| 6 | Le Breton, Maronnaud, Hallé, WebMole, WWW 2013 Companion | corrected | Third author was missing; pp. 245-248, demo track. |
| 7 | Pellegrino, Tschürtz, Bodden, Rossow, jÄk, RAID 2015 | confirmed | LNCS 9404, pp. 295-316; 86% on 13 apps. |
| 8 | Whittaker, Thomason, TSE 1994 | corrected | Vol. 20 no. 10, p. 812; "information-theoretic" softened. |
| 9 | Carrasco, Oncina, ICGI 1994 | corrected | DOI added; page range disputed between sources, marked unverified. |
| 10 | Carrasco, Oncina, RAIRO-ITA 1999 | confirmed | 33(1), pp. 1-19. |
| 11 | Mao et al., Machine Learning 105(2), 2016 | confirmed | DOI and pages match. |
| 12 | Mao et al., QFM 2012 (EPTCS 103) | confirmed | pp. 49-63, arXiv 1212.3873. |
| 13 | Stolcke, Omohundro, NIPS 5 1992 | confirmed | pp. 11-18. |
| 14 | Stolcke, Omohundro, ICGI 1994 | confirmed | arXiv cmp-lg/9409010. |
| 15 | Su et al., Stoat, FSE 2017 | confirmed | DOI added; 17-31% matches abstract. |
| 16 | Zheng et al., WebExplor, ICSE 2021 | confirmed | Full text: DFA, MBIE-EB curiosity, gestalt tag-sequence similarity with threshold. |
| 17 | Pan et al., Q-testing, ISSTA 2020 | confirmed | Full author list confirmed; neural state comparator confirmed. |
| 18 | Auer, Cesa-Bianchi, Fischer, ML 47 2002 | confirmed | DOI matches. |
| 19 | Chapelle, Li, NIPS 2011 | confirmed | pp. 2249-2257. |
| 20 | Atlidakis, Godefroid, Polishchuk, RESTler, ICSE 2019 | corrected | ICSE title has no hyphen; the arXiv preprint has a different title. |
| 21 | Suter, Wittern, HotWeb 2015 | unverified | Seen only in other papers' reference lists. |
| 22 | RESTSpecIT, arXiv 2402.05102 | corrected | Authors added (Decrop et al.); preprint only, venue not found. |
| 23 | traffic2openapi (Go tool) | confirmed | pkg.go.dev page exists as described; software, not a paper. |
| 24 | Luo, Hariri, Eloussi, Marinov, FSE 2014 | confirmed | Existence, authors, 201 commits / 51 projects confirmed; page range left unverified. |
| 25 | Romano et al., ICSE 2021 | confirmed | 235 tests, 62 projects, pp. 1585-1597, DOI match. |
| 26 | Corazza et al., arXiv 2108.13322 | corrected | Authors and ESEM 2021 venue added. |
| 27 | Applitools ignore / layout regions (docs) | confirmed | Documentation. |
| 28 | Percy ignore regions and animation freezing (docs) | corrected | "CSS masking" not confirmed, removed. |
| 29 | LambdaTest SmartUI ignoreBoxes / selectBoxes (docs) | confirmed | Newer docs use ignoreDOM / selectDOM. |
| 30 | Argos ignore changes (docs) | confirmed | Manual and automatic ignore confirmed. |
| 31 | Choudhary et al., ICST 2012 (added) | confirmed | Added during re-check; abstract level. |
| 32 | IBM patent US 9,298,850 B2 (added) | confirmed | Added during re-check; claim 1 read. |

Counts: confirmed 23, corrected 8, unverified 1, removed 0 (32 entries, of which 2 were added). One detail was removed rather than a citation: the Percy "CSS masking" claim.
