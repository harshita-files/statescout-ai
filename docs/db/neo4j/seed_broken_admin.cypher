// Example data: one completed run of test-apps/broken-admin.
//
// GENERATED from a real crawl — do not hand-edit. Regenerate with the
// snippet in docs/db/README.md so the example can never describe a graph
// the orchestrator would not actually produce.
//
// 6 states · 11 edges · 6 back-edges · 4 violations
//
//   cat docs/db/neo4j/migrations/001_init.cypher docs/db/neo4j/seed_broken_admin.cypher \
//     | docker exec -i statescout-neo4j cypher-shell -u neo4j -p statescout

MERGE (run:Run {run_id: "run-demo-0001"})
SET run += {
  target_url: "/index.html",
  role: "guest",
  status: 'completed',
  started_at: datetime('2026-08-09T12:00:00Z'),
  finished_at: datetime('2026-08-09T12:00:03Z'),
  termination_reason: "frontier_exhausted",
  depth_limit: 10,
  max_states: 50,
  state_count: 6,
  edge_count: 11,
  violation_count: 4,
  skipped_count: 0,
  replay_steps: 21,
  perception_mode: 'full',
  target_app: 'broken-admin'
};

// ---------- states ----------
MERGE (s:State {uid: "run-demo-0001:s-e03abf1f8b71"})
SET s += { run_id: "run-demo-0001", state_id: "s-e03abf1f8b71", url: "/index.html", title: "Acme — Home", role: "guest",
           depth: 0, screenshot_path: "/fake/screenshots/index.html.png", first_seen_at: datetime('2026-08-09T12:00:00Z') };
MERGE (s:State {uid: "run-demo-0001:s-d03538be6b9e"})
SET s += { run_id: "run-demo-0001", state_id: "s-d03538be6b9e", url: "/pages/admin.html", title: "Admin", role: "guest",
           depth: 3, screenshot_path: "/fake/screenshots/pages/admin.html.png", first_seen_at: datetime('2026-08-09T12:00:00Z') };
MERGE (s:State {uid: "run-demo-0001:s-2e84eeb854c6"})
SET s += { run_id: "run-demo-0001", state_id: "s-2e84eeb854c6", url: "/pages/dashboard.html", title: "Dashboard", role: "guest",
           depth: 2, screenshot_path: "/fake/screenshots/pages/dashboard.html.png", first_seen_at: datetime('2026-08-09T12:00:00Z') };
MERGE (s:State {uid: "run-demo-0001:s-70381d621815"})
SET s += { run_id: "run-demo-0001", state_id: "s-70381d621815", url: "/pages/login.html", title: "Sign in", role: "guest",
           depth: 1, screenshot_path: "/fake/screenshots/pages/login.html.png", first_seen_at: datetime('2026-08-09T12:00:00Z') };
MERGE (s:State {uid: "run-demo-0001:s-b1c0c3e5965f"})
SET s += { run_id: "run-demo-0001", state_id: "s-b1c0c3e5965f", url: "/pages/register.html", title: "Create account", role: "guest",
           depth: 2, screenshot_path: "/fake/screenshots/pages/register.html.png", first_seen_at: datetime('2026-08-09T12:00:00Z') };
MERGE (s:State {uid: "run-demo-0001:s-d8df0a7d6436"})
SET s += { run_id: "run-demo-0001", state_id: "s-d8df0a7d6436", url: "/pages/reports.html", title: "Reports", role: "guest",
           depth: 3, screenshot_path: "/fake/screenshots/pages/reports.html.png", first_seen_at: datetime('2026-08-09T12:00:00Z') };

MATCH (run:Run {run_id: "run-demo-0001"}), (s:State {run_id: "run-demo-0001"})
MERGE (run)-[:DISCOVERED]->(s);

MATCH (run:Run {run_id: "run-demo-0001"}), (s:State {uid: "run-demo-0001:s-e03abf1f8b71"})
MERGE (run)-[:SEEDED_AT]->(s);

// ---------- transitions ----------
// Cycles are preserved. Six of these eleven edges land on an already-
// discovered state; pruning them would turn the graph into a tree and
// destroy the evidence that admin is reachable by three routes.
MATCH (a:State {uid: "run-demo-0001:s-e03abf1f8b71"}), (b:State {uid: "run-demo-0001:s-70381d621815"})
CREATE (a)-[:TRANSITIONS_TO { run_id: "run-demo-0001", action_id: "592ce2094a71", label: "follow \"Sign in\"", is_back_edge: false }]->(b);
MATCH (a:State {uid: "run-demo-0001:s-70381d621815"}), (b:State {uid: "run-demo-0001:s-b1c0c3e5965f"})
CREATE (a)-[:TRANSITIONS_TO { run_id: "run-demo-0001", action_id: "7b48eaf48ea2", label: "follow \"Create an account\"", is_back_edge: false }]->(b);
MATCH (a:State {uid: "run-demo-0001:s-70381d621815"}), (b:State {uid: "run-demo-0001:s-2e84eeb854c6"})
CREATE (a)-[:TRANSITIONS_TO { run_id: "run-demo-0001", action_id: "87987ee53792", label: "click \"Sign in\"", is_back_edge: false }]->(b);
MATCH (a:State {uid: "run-demo-0001:s-b1c0c3e5965f"}), (b:State {uid: "run-demo-0001:s-70381d621815"})
CREATE (a)-[:TRANSITIONS_TO { run_id: "run-demo-0001", action_id: "6a0341f7fed4", label: "follow \"Back to sign in\"", is_back_edge: true }]->(b);
MATCH (a:State {uid: "run-demo-0001:s-2e84eeb854c6"}), (b:State {uid: "run-demo-0001:s-d03538be6b9e"})
CREATE (a)-[:TRANSITIONS_TO { run_id: "run-demo-0001", action_id: "2d92f08457eb", label: "follow \"Admin\"", is_back_edge: false }]->(b);
MATCH (a:State {uid: "run-demo-0001:s-2e84eeb854c6"}), (b:State {uid: "run-demo-0001:s-d8df0a7d6436"})
CREATE (a)-[:TRANSITIONS_TO { run_id: "run-demo-0001", action_id: "80c48f2131e1", label: "follow \"Reports\"", is_back_edge: false }]->(b);
MATCH (a:State {uid: "run-demo-0001:s-2e84eeb854c6"}), (b:State {uid: "run-demo-0001:s-70381d621815"})
CREATE (a)-[:TRANSITIONS_TO { run_id: "run-demo-0001", action_id: "a5202676403d", label: "click \"Log out\"", is_back_edge: true }]->(b);
MATCH (a:State {uid: "run-demo-0001:s-d03538be6b9e"}), (b:State {uid: "run-demo-0001:s-2e84eeb854c6"})
CREATE (a)-[:TRANSITIONS_TO { run_id: "run-demo-0001", action_id: "9534279ba450", label: "follow \"Back\"", is_back_edge: true }]->(b);
MATCH (a:State {uid: "run-demo-0001:s-d03538be6b9e"}), (b:State {uid: "run-demo-0001:s-70381d621815"})
CREATE (a)-[:TRANSITIONS_TO { run_id: "run-demo-0001", action_id: "a5202676403d", label: "click \"Log out\"", is_back_edge: true }]->(b);
MATCH (a:State {uid: "run-demo-0001:s-d8df0a7d6436"}), (b:State {uid: "run-demo-0001:s-2e84eeb854c6"})
CREATE (a)-[:TRANSITIONS_TO { run_id: "run-demo-0001", action_id: "9534279ba450", label: "follow \"Back\"", is_back_edge: true }]->(b);
MATCH (a:State {uid: "run-demo-0001:s-d8df0a7d6436"}), (b:State {uid: "run-demo-0001:s-70381d621815"})
CREATE (a)-[:TRANSITIONS_TO { run_id: "run-demo-0001", action_id: "a5202676403d", label: "click \"Log out\"", is_back_edge: true }]->(b);

// ---------- expectations ----------
MERGE (e:Expectation {uid: "run-demo-0001:e-admin-link"})
SET e += { run_id: "run-demo-0001", expectation_id: "e-admin-link", polarity: "must_not_exist",
           subject: "admin-link", roles: ["guest"], source_text: "A guest must never see the admin link." };
MERGE (e:Expectation {uid: "run-demo-0001:e-delete-user"})
SET e += { run_id: "run-demo-0001", expectation_id: "e-delete-user", polarity: "must_not_exist",
           subject: "delete-user", roles: ["guest"], source_text: "A guest must never be able to delete a user." };
MERGE (e:Expectation {uid: "run-demo-0001:e-debug-panel"})
SET e += { run_id: "run-demo-0001", expectation_id: "e-debug-panel", polarity: "must_not_exist",
           subject: "debug-panel", roles: [], source_text: "No page may ship a debug panel." };
MERGE (e:Expectation {uid: "run-demo-0001:e-skip-link"})
SET e += { run_id: "run-demo-0001", expectation_id: "e-skip-link", polarity: "must_exist",
           subject: "skip-to-content", roles: [], source_text: "Every page must offer a skip-to-content link." };

MATCH (run:Run {run_id: "run-demo-0001"}), (e:Expectation {run_id: "run-demo-0001"})
MERGE (run)-[:HAS_EXPECTATION]->(e);

// ---------- violations ----------
MERGE (v:Violation {uid: "run-demo-0001:v-s-2e84eeb854c6-e-admin-link"})
SET v += { run_id: "run-demo-0001", violation_id: "v-s-2e84eeb854c6-e-admin-link", clause_type: "forbidden_present",
           severity: "critical", rationale: "admin-link is present for role=guest",
           selector: "[data-tag=\"admin-link\"]", evidence_text: "admin-link",
           detected_at: datetime('2026-08-09T12:00:02Z') };
MATCH (v:Violation {uid: "run-demo-0001:v-s-2e84eeb854c6-e-admin-link"}), (s:State {uid: "run-demo-0001:s-2e84eeb854c6"}),
      (e:Expectation {uid: "run-demo-0001:e-admin-link"})
MERGE (v)-[:FOUND_IN]->(s)
MERGE (v)-[:BREACHES]->(e);
MERGE (v:Violation {uid: "run-demo-0001:v-s-d03538be6b9e-e-delete-user"})
SET v += { run_id: "run-demo-0001", violation_id: "v-s-d03538be6b9e-e-delete-user", clause_type: "forbidden_present",
           severity: "critical", rationale: "delete-user is present for role=guest",
           selector: "[data-tag=\"delete-user\"]", evidence_text: "delete-user",
           detected_at: datetime('2026-08-09T12:00:02Z') };
MATCH (v:Violation {uid: "run-demo-0001:v-s-d03538be6b9e-e-delete-user"}), (s:State {uid: "run-demo-0001:s-d03538be6b9e"}),
      (e:Expectation {uid: "run-demo-0001:e-delete-user"})
MERGE (v)-[:FOUND_IN]->(s)
MERGE (v)-[:BREACHES]->(e);
MERGE (v:Violation {uid: "run-demo-0001:v-s-d03538be6b9e-e-skip-link"})
SET v += { run_id: "run-demo-0001", violation_id: "v-s-d03538be6b9e-e-skip-link", clause_type: "required_absent",
           severity: "medium", rationale: "skip-to-content is missing for role=guest",
           selector: "", evidence_text: "",
           detected_at: datetime('2026-08-09T12:00:02Z') };
MATCH (v:Violation {uid: "run-demo-0001:v-s-d03538be6b9e-e-skip-link"}), (s:State {uid: "run-demo-0001:s-d03538be6b9e"}),
      (e:Expectation {uid: "run-demo-0001:e-skip-link"})
MERGE (v)-[:FOUND_IN]->(s)
MERGE (v)-[:BREACHES]->(e);
MERGE (v:Violation {uid: "run-demo-0001:v-s-d8df0a7d6436-e-debug-panel"})
SET v += { run_id: "run-demo-0001", violation_id: "v-s-d8df0a7d6436-e-debug-panel", clause_type: "forbidden_present",
           severity: "critical", rationale: "debug-panel is present for role=guest",
           selector: "[data-tag=\"debug-panel\"]", evidence_text: "debug-panel",
           detected_at: datetime('2026-08-09T12:00:02Z') };
MATCH (v:Violation {uid: "run-demo-0001:v-s-d8df0a7d6436-e-debug-panel"}), (s:State {uid: "run-demo-0001:s-d8df0a7d6436"}),
      (e:Expectation {uid: "run-demo-0001:e-debug-panel"})
MERGE (v)-[:FOUND_IN]->(s)
MERGE (v)-[:BREACHES]->(e);
