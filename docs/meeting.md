# Meeting runbook — Track B, Months 0–2

A screen-share script. Every command here was run and its output checked; the one
exception is flagged. Times assume you talk while things run.

**Total: ~18 minutes of demo, or ~6 if you're squeezed.** The 6-minute path is
marked ⭐.

---

## Before the meeting (5 minutes, do this first)

```bash
cd ~/Projects/final-year-project/statescout-ai
git status                       # should be clean
uv sync --all-groups             # in case anything is stale
uv run pytest -q                 # 372 passed — if not, stop and fix before demoing
uv run python docs/demo_crawl.py # the centrepiece; confirm it prints EXACT MATCH
```

Then:

- **Terminal font size up.** Nobody can read 11pt on a shared screen. 16–18pt.
- **Two tabs open:** one terminal, one browser.
- **Browser tab 1:** open `test-apps/broken-admin/index.html` directly from disk
  (`file:///home/kr95/Projects/final-year-project/statescout-ai/test-apps/broken-admin/index.html`).
  The relative links work from `file://` — no server needed.
  *(If you prefer a server: `python3 -m http.server 4173 --directory test-apps/broken-admin`.
  I could not verify this one — my sandbox blocks port binding — so test it yourself first.)*
- **Browser tab 2:** [mermaid.live](https://mermaid.live), empty, for beat 5.
- `clear` between beats. A clean screen reads as a clean project.

---

## The one-sentence version

> I built the orchestrator — the part that decides where the crawler goes, when to
> stop, and what counts as a violation. It's done through Month 2 of four: it
> autonomously crawls a web app, builds a cyclic state graph, and finds every
> planted policy violation with no false positives.

If someone asks "is it working?" before you've started: **run beat 3.** It answers
the question in 20 seconds.

---

## Beat 1 ⭐ — What the thing is (1 min, no terminal)

Say this before touching anything:

> Most UI testing checks that a workflow succeeds. StateScout checks the opposite:
> that certain things **never appear**. An admin link visible to a guest, a debug
> panel in production. The backend might correctly reject the request — but the
> link being on screen is already the leak.
>
> My track is the brain: the exploration loop and the decision-making. The
> browser, the vision model, and the database belong to three teammates. None of
> their code exists yet — and everything I'm about to show you runs anyway. That's
> the design, not a workaround.

That last point is the strongest thing you have. Lead with it.

---

## Beat 2 ⭐ — The broken app (2 min, browser)

Switch to the browser tab with `index.html`. Click **Sign in** → **Sign in** to
reach the dashboard.

Point at the **Admin** link:

> I'm logged in as a guest. That link should not be here. It's planted — one of
> four deliberate bugs.

Click **Admin**. Point at the **Delete user** button:

> Two clicks from the front page, as a guest. That's the second one.

Then show the file that makes this rigorous:

```bash
cat test-apps/broken-admin/violations.json
```

> Every defect is written down *before* the crawl runs — the page, the rule it
> breaks, and why. So the test can assert we found all four **and invented none**.
> A tool that cries wolf is one nobody reads.

---

## Beat 3 ⭐ — The crawl finds them (3 min, the centrepiece)

```bash
uv run python docs/demo_crawl.py
```

Runs in about a second. Walk the output top to bottom:

**The graph.** Six states, eleven edges, six marked `(back-edge, cycle closed)`.

> Those back-edges matter more than they look. Logging out from the dashboard
> takes you back to login — that's a cycle. The obvious implementation prunes
> those to keep the graph a tree, and that quietly destroys the evidence, because
> "you can reach admin from three different paths" *is* the finding.

**The findings.** Four green `FOUND`, nothing red.

> Three of these are "this must not exist". The fourth, V-04, is the opposite —
> a required accessibility link that's *missing* from one page. Those are
> different set operations, and an earlier version of our interface could only
> express the first one. Catching that before we froze the contract is one of the
> things I'd point at from this month.

**The summary.** Land on two lines:

```
(state, action) pairs executed   11
distinct pairs claimed           11   <- NFR-05: equal means zero duplicates
```

> That equality *is* the no-duplicate-work requirement. Executions versus distinct
> pairs — they can only match if nothing ran twice.

---

## Beat 4 — Two implementations, one behaviour (2 min)

```bash
uv run pytest tests/unit/orchestrator/test_explore.py -k dod -o addopts="" -v --no-header
```

Output shows each test twice — `[reference]` and `[langgraph]`:

```
test_dod_a_the_loop_terminates_on_an_app_with_cycles[reference] PASSED
test_dod_a_the_loop_terminates_on_an_app_with_cycles[langgraph] PASSED
test_dod_b_every_state_action_pair_executes_exactly_once[reference] PASSED
test_dod_b_every_state_action_pair_executes_exactly_once[langgraph] PASSED
test_dod_c_the_login_register_cycle_records_its_back_edge[reference] PASSED
test_dod_c_the_login_register_cycle_records_its_back_edge[langgraph] PASSED
```

> I wrote the loop twice. Once in plain Python so the logic can be read and
> argued about, once in LangGraph so it can be checkpointed and resumed after a
> crash. The whole test suite runs against **both** — so they can't drift apart.
> The plain one is deprecated for production but I kept it deliberately: it's the
> reference the framework version is held to.

---

## Beat 5 — The state machine, drawn (2 min)

```bash
uv run python -c "
from apps.agent.orchestrator.graph_runner import build_graph
from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.deps import fake_ports
from apps.agent.orchestrator.fakes import DEFAULT_POLICY
print(build_graph(fake_ports(), DEFAULT_POLICY, OrchestratorConfig(_env_file=None)).get_graph().draw_mermaid())
"
```

Copy the output into the **mermaid.live** tab. You get a rendered diagram of
Scan → Reason → Act → Observe with the conditional edges.

> Four nodes. `Scan` looks at a page, `Reason` decides whether it violates
> anything, `Act` picks the next thing to click, `Observe` records the edge. The
> dotted lines are the conditional edges — that's where "keep going" versus "stop"
> gets decided.
>
> The `observe → act` edge is the one I'd point out: when an action fails or can't
> be safely retried, we go back and pick another *without* re-scanning. Getting
> that wrong would have double-counted states.

*(Diagram note: `clean` and `violated` both route to `act`, so Mermaid draws one
arrow. A violation doesn't stop the crawl — coverage is the point.)*

---

## Beat 6 — The guardrail (1 min, this one gets a reaction)

```bash
echo '{"tool_name":"Write","tool_input":{"file_path":"apps/agent/crawler/x.py"},"cwd":"'"$PWD"'"}' \
  | python3 .claude/hooks/track_b_paths.py; echo "exit=$?"
```

```
track-guard: Track B may not write apps/agent/crawler/x.py. That path belongs to
Track A. Writable here: apps/agent/orchestrator/, apps/agent/skeleton.py, ...
exit=2
```

> Four of us in one repo. This hook blocks any write outside my track's folders —
> it's enforced by the tooling, not by me remembering. It knows all four tracks,
> so everyone gets the same protection. It also refuses to edit *itself*, so a
> session can't quietly widen its own permissions.

---

## Beat 7 — CI-shaped output (1 min)

```bash
uv run python -m apps.agent.skeleton --fake ; echo "exit=$?"
```

> JSON report on stdout, exit code 1 because it found a violation. Logs go to
> stderr, so this pipes into `jq` and fails a build step without anyone parsing
> anything.

Then show the log stream separately:

```bash
uv run python -m apps.agent.skeleton --fake --run-id demo 2>&1 >/dev/null | head -4
```

> Every line is JSON, every line carries the run id. That's what the reporting API
> will read.

---

## Beat 8 ⭐ — Close on the numbers (1 min)

```bash
uv run pytest -q && git log --oneline -10
```

> 372 tests, about three seconds. Ten commits, Months 0 through 2 of four.
> Next up is the natural-language policy pipeline — a QA engineer types a rule in
> English and it becomes something the machine can check.

---

## Questions you'll get, and honest answers

**"Does it work on a real website?"**
> Not yet, and that's expected at this point. The browser layer is another
> teammate's track. Everything I built runs against an in-memory stand-in that
> implements the exact same interface, so when their crawler lands it's a
> one-line swap. That's why I could finish two months of work without waiting on
> anyone.

**"Isn't that just testing your own fake?"**
> Fair challenge. Two answers. The fake implements the agreed interface, and a
> test checks it method-by-method against that interface — signatures included,
> not just names. And the demo app has ground truth written down independently
> of the code, so the crawl is scored against a file, not against itself.

**"Why did you write the same loop twice?"**
> Because the framework version can't be read in one sitting. The plain one is
> the specification; the framework one is what ships because it can survive a
> crash. Both run the same tests, so if they ever disagree, that's a failing
> test, not a surprise in production.

**"What was the hardest part?"**
> Breadth-first search with one browser. BFS says visit the oldest queued action
> next — but that action is on a page the browser has already navigated away
> from. So you have to re-navigate by replaying the path from the start. Except
> replaying re-fires every action on that path, and if one of them submitted a
> form you've just placed a second order in the app you're auditing. I ended up
> allowing replay only for pure navigation, and anything behind a form submit is
> reported as unexplored rather than reached unsafely. Reported, not silently
> dropped — that distinction is the whole thing.

**"How do you know it terminates?"**
> There's a written proof sketch at the top of `explore.py`, and the adversarial
> cases are tests: self-loops, a diamond where every page reaches every other, a
> hundred-page chain, a fifty-way fan-out, and a deliberately broken fingerprint
> that makes every page load look like a new state.

**"What's not done?"**
> Months 3 and 4: turning English policies into rules, graceful stop, and
> resume-after-crash. And four cross-team questions are open — one of them blocks
> freezing the shared interface. They're all written up in
> `docs/adr-001-cross-track-contract-review.md` with an owner each.

---

## If something breaks live

- **Any command fails** → `git status` first. If dirty, `git stash`.
- **Demo script fails** → fall back to `uv run pytest tests/integration -q`. Same
  guarantees, less pretty.
- **Everything fails** → `uv run pytest -q`. If that's green, the project is fine
  and it's an environment problem; say so and move on. Don't debug on stage.

---

## Two things worth saying out loud

Supervisors remember judgement, not line counts. Both of these are about
decisions, not code. Read the explanation, then say the short version.

### 1. Four things the shared interface could not express

**Context to give them first:** four people are building four pieces that must
plug together — browser driver, orchestrator, vision model, database. Before
anyone writes code you agree the interface: the exact functions each piece
exposes. That file gets frozen, because changing it later breaks three people.
Going through it before the freeze turned up four gaps.

| Gap | What would have happened |
| --- | --- |
| The audit function only received the **forbidden** list | "Is a forbidden thing present?" cannot also answer "is a required thing missing?" — they are different operations. **V-04 in the demo would have been undetectable**, not just hard |
| There was a way to **ask** "already clicked this?" but no way to **record** it | A guest list you can check but never add names to. The crawler re-clicks forever |
| One function did **two jobs** — go to a URL, and click a button | A page timing out is worth retrying; a vanished button is not. One function, one error type, no way to tell them apart |
| The vision model and the database each mint a **state id**, and nothing said they must match | Violations get filed against an id the database never heard of. **The report comes back empty while the crawl works perfectly** |

The first one is the strongest and it was the team's call, not mine to claim
alone — worth saying so. The fourth is still open and blocks the freeze.

**Say:**

> Before we locked the shared interface I went through it looking for things it
> couldn't express, and found four. The clearest: the audit function only
> accepted a list of forbidden elements, so there was no way to check that a
> *required* element was missing — one of our own requirements would have been
> undeliverable. All four are written up with an owner each.

### 2. The safety rule and the search strategy contradicted each other

**The safety rule.** Never perform the same action twice. We are clicking around
inside a real application; "Submit order" twice means two orders.

**The search strategy.** Breadth-first — everything one click from the home page,
then everything two clicks away. Even coverage, shallow bugs found fast.

**Why they collide.** Breadth-first means the next queued action is usually on a
page you have already navigated away from. One browser: you cannot click a button
on a page you are not looking at. So you go back to the start and re-click your
way there — and that **re-performs every action on the path**. If the path went
through a form submit, you just submitted it again. The search strategy breaks
the safety rule.

**The resolution.** Only pure navigation may be replayed — links, back, menu
items. Clicking a link twice does nothing. Forms are never re-submitted.

**The cost, stated plainly.** A page reachable only *through* a form submit cannot
be returned to, so what lies behind it goes unexplored. The system reports it as
a coverage gap with a reason, rather than skipping it silently or re-submitting
to reach it.

**Say:**

> Breadth-first search needs you to return to pages you've left, and the only way
> back is to re-click the path — which re-fires those actions. That conflicts with
> never repeating an action, which exists because we're inside a live app. I
> allowed replay only for pure navigation. The trade-off is real: anything behind
> a form submit doesn't get explored, and the system reports that as a coverage
> gap rather than hiding it.

**If pushed — "so your coverage isn't complete?":**

> Correct, and it says so. A crawler that silently re-submits forms to claim
> complete coverage is worse than one that tells you which part it couldn't
> safely reach.
