// The queries the product actually needs.
//
// Grouped by who asks. Each one names the API endpoint or requirement it serves,
// so a query nobody calls is visibly dead rather than quietly kept.
//
// `$run_id` etc. are parameters — never string-concatenate them into Cypher.

// ===========================================================================
// The extension's run list  ·  GET /runs
// ===========================================================================

MATCH (r:Run)
RETURN r.run_id            AS runId,
       r.target_url        AS targetUrl,
       r.role              AS role,
       r.status            AS status,
       r.started_at        AS startedAt,
       r.finished_at       AS finishedAt,
       r.termination_reason AS terminationReason,
       { states: r.state_count, edges: r.edge_count,
         violations: r.violation_count, skippedActions: r.skipped_count } AS counts
ORDER BY r.started_at DESC
LIMIT $limit;

// ===========================================================================
// The graph view  ·  GET /runs/{runId}/graph
// ===========================================================================

// Nodes and edges in two result sets rather than one path expansion: the
// extension renders them as separate arrays, and a path query would return the
// same node once per path it appears on.
MATCH (s:State {run_id: $run_id})
RETURN s.state_id AS stateId, s.url AS url, s.title AS title,
       s.role AS role, s.depth AS depth,
       s.screenshot_path AS screenshotPath, s.first_seen_at AS firstSeenAt
ORDER BY s.depth, s.url;

MATCH (a:State {run_id: $run_id})-[t:TRANSITIONS_TO]->(b:State {run_id: $run_id})
RETURN a.state_id AS fromStateId, b.state_id AS toStateId,
       t.action_id AS actionId, t.label AS label, t.is_back_edge AS isBackEdge;

// ===========================================================================
// The report  ·  GET /runs/{runId}/report
// ===========================================================================

MATCH (v:Violation {run_id: $run_id})-[:FOUND_IN]->(s:State)
MATCH (v)-[:BREACHES]->(e:Expectation)
RETURN v.violation_id AS violationId,
       s.state_id     AS stateId,
       s.url          AS url,
       e.expectation_id AS expectationId,
       e.source_text  AS policyClause,     // NFR-14: quote the rule back
       v.clause_type  AS clauseType,
       v.severity     AS severity,
       v.rationale    AS rationale,
       { selector: v.selector, text: v.evidence_text,
         screenshotPath: v.screenshot_path } AS evidence,
       v.detected_at  AS detectedAt
ORDER BY CASE v.severity
           WHEN 'critical' THEN 0 WHEN 'high' THEN 1
           WHEN 'medium'   THEN 2 ELSE 3 END,
         s.url;

// ===========================================================================
// Reproduction steps — the most valuable query here
// ===========================================================================

// "How does a guest actually reach this?" A violation with no route to it is a
// finding a developer will argue with. This returns the shortest click-path from
// the seed, which is the bug report.
//
// The upper bound on length is not decoration: the graph is CYCLIC, and an
// unbounded variable-length match over a cyclic graph is how you hang the
// database.
MATCH (run:Run {run_id: $run_id})-[:SEEDED_AT]->(seed:State)
MATCH (target:State {uid: $run_id + ':' + $state_id})
MATCH path = shortestPath((seed)-[:TRANSITIONS_TO*..15]->(target))
RETURN [n IN nodes(path) | n.url]              AS pages,
       [r IN relationships(path) | r.label]    AS clicks,
       length(path)                            AS clickCount;

// Every distinct route, not just the shortest — "reachable three different ways"
// is often the finding itself. Bounded and capped for the same reason.
MATCH (run:Run {run_id: $run_id})-[:SEEDED_AT]->(seed:State)
MATCH (target:State {uid: $run_id + ':' + $state_id})
MATCH path = (seed)-[:TRANSITIONS_TO*..8]->(target)
WHERE all(n IN nodes(path) WHERE single(m IN nodes(path) WHERE m = n))  // simple paths only
RETURN [r IN relationships(path) | r.label] AS clicks, length(path) AS clickCount
ORDER BY clickCount
LIMIT 10;

// ===========================================================================
// Cycles  ·  proving the graph is not a tree
// ===========================================================================

MATCH (a:State {run_id: $run_id})-[t:TRANSITIONS_TO {is_back_edge: true}]->(b:State)
RETURN a.url AS from, t.label AS via, b.url AS to
ORDER BY a.url;

// States you can leave and return to. The demo app has several; a login/logout
// pair is the canonical one.
MATCH (s:State {run_id: $run_id})
MATCH cycle = (s)-[:TRANSITIONS_TO*2..6]->(s)
RETURN s.url AS state, length(cycle) AS cycleLength,
       [r IN relationships(cycle) | r.label] AS route
ORDER BY cycleLength
LIMIT 20;

// ===========================================================================
// Coverage  ·  what the crawl did not reach
// ===========================================================================

// A state with no outgoing edges is either a genuine dead end or the depth limit
// biting. Cross-check against Run.termination_reason before reporting either.
MATCH (s:State {run_id: $run_id})
WHERE NOT (s)-[:TRANSITIONS_TO]->()
RETURN s.url AS deadEnd, s.depth AS depth
ORDER BY s.depth DESC;

// Deepest states reached — if these sit exactly at depth_limit, the crawl was
// truncated and coverage claims need qualifying.
MATCH (r:Run {run_id: $run_id})-[:DISCOVERED]->(s:State)
RETURN max(s.depth) AS deepest, r.depth_limit AS limit,
       max(s.depth) >= r.depth_limit AS possiblyTruncated;

// ===========================================================================
// Cross-run comparison  ·  FR-31, the role diff
// ===========================================================================

// The join is on `state_id`, never `uid`: the fingerprint is what two runs share.
// Note that a role-gated page renders different DOM and therefore fingerprints
// differently, so a state present in one run and absent from the other is
// exactly the signal being looked for.
MATCH (a:State {run_id: $run_a})
OPTIONAL MATCH (b:State {run_id: $run_b, state_id: a.state_id})
WITH a, b WHERE b IS NULL
RETURN a.url AS onlyInFirstRun, a.role AS role, a.depth AS depth
ORDER BY a.depth;

// Violations that appear for one role and not the other.
MATCH (v:Violation {run_id: $run_a})-[:BREACHES]->(e:Expectation)
WHERE NOT EXISTS {
  MATCH (v2:Violation {run_id: $run_b})-[:BREACHES]->(e2:Expectation)
  WHERE e2.expectation_id = e.expectation_id
}
RETURN e.expectation_id AS onlyForFirstRole, v.severity AS severity, count(*) AS occurrences;

// ===========================================================================
// The control projection  ·  derived, run after a crawl completes
// ===========================================================================

// ADR-001 decision 1 justified content-addressed action ids partly by
// cross-state analytics. This is that payoff — and it is a projection so the
// write path stays minimal.
MATCH (a:State {run_id: $run_id})-[t:TRANSITIONS_TO]->()
MERGE (c:Control {action_id: t.action_id})
  ON CREATE SET c.label = t.label
MERGE (a)-[:EXPOSES]->(c);

// "Where does Log out appear?" — one control, many states.
MATCH (s:State {run_id: $run_id})-[:EXPOSES]->(c:Control {action_id: $action_id})
RETURN c.label AS control, collect(s.url) AS appearsOn;

// Controls that appear on many pages are the shared navigation. Controls that
// appear once are the interesting ones.
MATCH (s:State {run_id: $run_id})-[:EXPOSES]->(c:Control)
WITH c, count(s) AS pages
RETURN c.label AS control, pages
ORDER BY pages DESC;

// ===========================================================================
// Housekeeping
// ===========================================================================

// Delete one run. Detach-delete in batches: a large crawl is enough nodes to
// blow the default transaction memory in a single statement.
MATCH (n)
WHERE n.run_id = $run_id
CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 1000 ROWS;

// Runs older than the retention window, oldest first.
MATCH (r:Run)
WHERE r.started_at < datetime() - duration({days: $retention_days})
RETURN r.run_id AS runId, r.started_at AS startedAt
ORDER BY r.started_at;

// Integrity: every state except the seed should have an inbound edge. A result
// here means something wrote a node the crawler never explained how it reached.
MATCH (r:Run {run_id: $run_id})-[:DISCOVERED]->(s:State)
WHERE NOT (()-[:TRANSITIONS_TO]->(s)) AND NOT (r)-[:SEEDED_AT]->(s)
RETURN s.url AS orphanedState, s.depth AS depth;
