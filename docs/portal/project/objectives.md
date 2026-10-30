# Objectives

## Primary objective

Deliver a **local-first** auditing tool, driven from inside VS Code, that
autonomously explores a running web application, builds a graph of every UI state
it reaches, and reports each state that violates a natural-language policy - with
screenshot and structural evidence for every finding.

## Specific objectives

1. **Autonomous exploration.** Crawl an application breadth-first without scripted
   paths, and terminate on its own - never loop forever on a cycle.
2. **A faithful state model.** Record the application as a *cyclic* directed graph:
   one node per distinct UI state, one edge per action taken. Back-edges are
   evidence about the application's navigation, never pruned.
3. **Semantic perception.** Interpret each state - DOM, accessibility tree and
   screenshot - into the elements and capabilities a user in a given role can see.
4. **Policy from plain English.** Turn a QA engineer's sentences into clauses of two
   kinds: things that must *not* exist, and things that *must*.
5. **Negation-aware auditing.** Detect forbidden elements that are present and
   required elements that are absent, deciding presence deterministically.
6. **Evidence-backed reports.** Every violation carries the path that reaches it, a
   screenshot, the clause it breaks, and the reasoning behind the verdict.
7. **Research contribution.** Evaluate whether a fine-tuned open model (InternVL)
   improves negation accuracy over a general-purpose one (Gemini), on an isolated
   track that cannot delay the product.

## Requirements the system is measured against

Requirement IDs refer to the project's Software Requirements Specification.

| ID | Requirement | How it is checked |
| --- | --- | --- |
| FR-04 | Parse a plain-English policy into clauses | policy parser output vs. hand-written ground truth |
| FR-10 | Configurable exploration depth limit | orchestrator configuration tests |
| FR-18 | Flag a forbidden element that is present | planted violations in the ground-truth test apps |
| FR-19 | Flag a required element that is absent | planted violations in the ground-truth test apps |
| NFR-01 | Fingerprint a captured state in under 500 ms | performance tests on multi-megabyte pages |
| NFR-05 | 0% duplicate exploration of a `(state, action)` pair | measured from the recorded graph on every crawl |
| NFR-08 | The vision model is replaceable | one provider interface; Gemini and InternVL both plug in |
| NFR-10 | Local-first: nothing leaves the machine unless a hosted model is enabled | deployment configuration |
| NFR-11 | Credentials never written to disk or logs | configuration and logging review |
| NFR-14 | Every violation carries a full evidence chain | report contract and end-to-end tests |

## Scope

**In scope:** autonomous crawling, DOM + accessibility + screenshot perception,
vision-language interpretation, the cyclic state graph in Neo4j, the negation
engine with a deterministic cross-check, policy parsing, structured reports, the
VS Code extension, a local reporting API, Docker Compose deployment, tests and
documentation.

**Out of scope for v1:** a hosted multi-tenant service, mobile applications, and
backend / API security or penetration testing.
