# `broken-admin` — six pages, four planted violations, two cycles

The ground-truth app. Every defect in it is deliberate, documented, and asserted
against. If StateScout misses one, StateScout is wrong. If StateScout reports a
fifth, StateScout is wrong. An *undocumented* bug in these pages is a bug in the
fixture, not a discovery.

## Running it

Static HTML, no build, no JavaScript beyond `onsubmit="return false"`:

```bash
python3 -m http.server 4173 --directory test-apps/broken-admin
# then seed a crawl at http://localhost:4173/index.html
```

## The three files that make it ground truth

| File | What it is |
| --- | --- |
| `app.json` | The machine-readable twin of the HTML: pages, `data-tag` elements, and the controls the accessibility tree exposes |
| `policy.json` | The QA engineer's English policy and its structured form |
| `violations.json` | Every planted defect, with the page it lives on and the clause it breaks |

`app.json` is checked against the HTML by
`tests/integration/orchestrator/test_test_app_consistency.py` — remove the admin
link and forget to update the JSON and that suite fails immediately, rather than
three weeks later when the live crawler finds one fewer violation than the fakes.

When Track A's Playwright crawler lands, `app.json` becomes the specification it
must reproduce from the real pages. A disagreement between the two is a genuine
finding about one of them.

## The graph

```
index ──▶ login ◀──▶ register
            │
            ▼
        dashboard ──▶ reports ──▶ dashboard
            │  │
            │  └───▶ admin ────▶ dashboard
            │
            └──▶ login          (log out)
```

Six states, four cycles. The cycles are the point: an implementation that prunes
back-edges to make this a tree still passes a naive "did it find the violations"
test while destroying the state-space evidence the audit is built on.

## The planted violations

| ID | Page | Clause | Why it is a violation |
| --- | --- | --- | --- |
| V-01 | `pages/dashboard.html` | `e-admin-link` (forbidden present) | The Admin link renders for every role. The backend rejects the request — the *link* is the exposure. |
| V-02 | `pages/reports.html` | `e-debug-panel` (forbidden present) | A debug panel left in the production build. |
| V-03 | `pages/admin.html` | `e-delete-user` (forbidden present) | A destructive control a guest can reach in two clicks. |
| V-04 | `pages/admin.html` | `e-skip-link` (required absent) | The skip-to-content link every other page carries is missing. |

V-01 through V-03 are marked with a `PLANTED V-nn` comment in the source. V-04
cannot be — it is an absence — so a test asserts the absence directly, and
asserts every *other* page has the link, so the fixture is not accidentally right.

V-04 exists to exercise **FR-19**. An intersection-only audit (`S ∩ forbidden`)
structurally cannot express "a required thing is missing"; without a planted
absence, the `required` half of `ExpectationSet` would never be tested.

## Known limitation this app surfaces

`ExpectationNode` scopes a clause by **role**, and by nothing else. A realistic
policy says *"every signed-in page must offer a way to log out"* — but there is no
way to say "signed-in page", so such a clause fires on `/index.html` and
`/pages/login.html` too, where a logout button correctly does not exist.

The demo policy sidesteps this by requiring `skip-to-content`, which genuinely
belongs on every page. The underlying gap is real: **FR-19 needs a scope
predicate on `ExpectationNode`** before a QA engineer can write the policy they
actually mean. Raised for Track C and the SRS; see `docs/adr-001-cross-track-contract-review.md`.
