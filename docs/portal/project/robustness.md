# Robustness on dynamic applications

Real web applications rarely render the same page twice. News feeds reorder, like
counts tick up, "updated 3 minutes ago" changes every minute, adverts rotate, and
some frameworks generate fresh class names on every load. Content can also arrive
over the network after the page reports that it has loaded, and the same click can
lead to different screens on different occasions.

A crawler that identifies a state by hashing everything it sees treats each of
these variations as a brand-new state, wastes its budget re-exploring them, and
loses track of where a replayed path really went. StateScout adds the following to
stay reliable on such applications.

All of it is **opt-in and off by default**. With it switched off, the system behaves
exactly as before, and the existing tests prove it.

## What was added

### 1. Stable state identity, without hiding evidence

Volatile parts of a page can be masked out of the state identity using
**application-specific patterns** (regular expressions) that a person reviews and
approves. Masks are applied only to page text and accessibility-tree text; the
role and the URL always stay part of the identity, and nothing is guessed to be
volatile automatically.

Masking affects **which captures count as the same state**, never what is audited.
The original, unmasked capture is still what the negation engine checks, so a
forbidden element can never be hidden by a mask.

### 2. Learned suggestions for what is volatile

Repeated captures of the same state are split into regions of the page, and the
regions that keep changing between captures are detected automatically. From these,
StateScout **suggests** masks. Suggestions are never applied on their own: a person
approves them into the configuration first, because changing identities in the
middle of a run would disconnect states that were already explored.

### 3. Pages are captured when they are ready

Before taking a capture, the crawler can wait for the page to settle: the page
structure unchanged for 200 ms, no network requests in flight, and no new requests
for 200 ms. The wait is capped at two seconds, so a page that never goes quiet is
still captured. Each capture records whether it was **ready, incomplete or unknown**,
so a partially loaded capture is visible in the results instead of passing silently.

### 4. Transition probabilities

Every time an action is taken, the state it leads to is counted. From these counts,
StateScout estimates how likely each outcome is:

> **P(next state t | state s, action a) = times a led from s to t / times a was taken from s**

Transitions observed while replaying a path are counted separately as well, so the
exploration-only picture can always be recovered. For analysis, a smoothed version
of the model keeps rare outcomes from being declared impossible just because they
have not been seen yet.

### 5. Replay that tolerates non-determinism

To reach an action deep in the application, the crawler replays the path that led
there. On a dynamic application the replay sometimes lands on a different screen.
When it lands on a state that is already known, that outcome has been seen at least
5% of the time (configurable), and the same control is present, the action is taken
from where the crawler actually is. Otherwise the step is recorded as a coverage gap.
An edge is never attributed to the wrong state.

### 6. Exploring the least-understood actions first

Within each depth level of the breadth-first search, actions whose outcome is
unknown or uncertain are tried before well-understood ones. This only **reorders**
work: no action is ever added or dropped, and termination still comes from the
visited set and the depth and state limits.

### 7. API endpoint and click statistics

The crawler can observe the network requests each action triggers. Requests are
reduced to a safe endpoint template such as `GET /users/:id/items/:uuid`: the host,
query values, headers and bodies are never recorded, and numeric and UUID path
segments become placeholders. For every endpoint, StateScout counts the **calls**
made, the **actions** that triggered it and how many of those were **clicks**,
overall and per state and action, with replayed traffic counted separately.

### 8. A confidence for every violation

A violation seen on one capture of a state but not on another is still reported,
with a measure of how consistently it appears:

> **recurrence = (times the violation was seen + 1) / (times the state was audited + 2)**
>
> **reproducibility = how reliably the actions leading into the state actually reach it**
>
> **confidence = recurrence × reproducibility**

An analysis helper also labels each finding **stable**, **flaky** or
**insufficient evidence**, using at least five observations before claiming either
way. These numbers describe how consistently a finding appears, not how likely it is
to be a real security issue, and a low score never suppresses a finding.

### 9. Statistics in the report

A scan can be started with the dynamic model switched on and its approved patterns
supplied. The run's statistics (transition counts and probabilities, endpoint
counts, capture readiness, and violation confidences) are stored with the scan and
returned alongside its report.

## What stays the same

- The exploration graph is still a **cyclic** directed graph: every traversal is
  recorded, back-edges included, and statistics sit beside the graph rather than
  replacing it.
- Loop prevention is still the visited set of `(state, action)` pairs, claimed
  before each action runs. Probabilities never decide when exploration stops; the
  depth and state limits still apply.
- Every original capture of a known state is audited, including revisits and
  replayed captures, so equivalence can save exploration work but never skips an
  audit.

## Turning it on

| Setting | Default | Effect |
| --- | --- | --- |
| `probabilistic_states` | off | enables everything on this page |
| `volatility_patterns` | none | the approved masking patterns |
| `replay_min_probability` | 0.05 | how often an outcome must have been seen before replay may continue from it |

These are settings of the orchestrator, and `probabilistic_states` and
`volatility_patterns` can also be passed when a scan is started through the API.
The design and its safeguards are recorded in full in
[ADR-002](../documentation/decisions/adr-002.md); the code is documented in the
[orchestrator reference](../reference/python/orchestrator.md).
