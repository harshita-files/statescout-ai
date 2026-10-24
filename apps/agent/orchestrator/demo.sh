#!/usr/bin/env bash
# StateScout AI — one-command demo.
#
#   ./demo.sh           run straight through
#   ./demo.sh --step    pause before each beat (press Enter) — use this live
#   ./demo.sh --quick   skip the full test suite (~20s) and the dynamic-app beat
#
# Fully offline: no Docker, Neo4j, Redis, browser or API keys needed. It runs the
# real orchestrator against the broken-admin ground-truth app with scripted
# crawler/perception fakes (see docs/meeting.md for the talking points).
# Works from any location inside the repo: it walks up to find pyproject.toml.

set -u
root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
while [ ! -f "$root/pyproject.toml" ] && [ "$root" != "/" ]; do root=$(dirname "$root"); done
[ -f "$root/pyproject.toml" ] || { echo "repo root (pyproject.toml) not found" >&2; exit 1; }
cd "$root" || exit 1

STEP=0 QUICK=0
for arg in "$@"; do
  case "$arg" in
    --step) STEP=1 ;;
    --quick) QUICK=1 ;;
    -h|--help) sed -n '2,11p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

B=$'\033[1m' D=$'\033[2m' G=$'\033[32m' R=$'\033[31m' C=$'\033[36m' X=$'\033[0m'
FAILED=0
export PYTHONWARNINGS=ignore
PYTEST=(uv run pytest -o addopts="--strict-markers" -q -W ignore --no-header)

beat() {
  printf '\n%s━━ %s ━━%s\n' "$B$C" "$1" "$X"
  [ -n "${2:-}" ] && printf '%s%s%s\n' "$D" "$2" "$X"
  if [ "$STEP" = 1 ]; then read -r -p "${D}[Enter to run]${X} " _ || true; fi
  printf '\n'
}
show() { printf '%s$ %s%s\n' "$D" "$*" "$X"; }
ok()   { printf '\n%s✔ %s%s\n' "$G" "$1" "$X"; }
bad()  { printf '\n%s✘ %s%s\n' "$R" "$1" "$X"; FAILED=1; }

# ── Preflight ───────────────────────────────────────────────────────────────
command -v uv >/dev/null || { echo "${R}uv not found — install it first${X}" >&2; exit 1; }
[ -d .venv ] || { echo "Creating environment (uv sync)…"; uv sync -q || exit 1; }

printf '%s\nStateScout AI%s — autonomous web-UI auditor\n' "$B" "$X"
printf '%sLangGraph orchestrator · cyclic exploration graph · polarity-typed policy oracle%s\n' "$D" "$X"

# ── 1. Baseline ─────────────────────────────────────────────────────────────
if [ "$QUICK" = 0 ]; then
  beat "1 · The baseline: full test suite" "Everything below is backed by tests that run on every commit."
  show "uv run pytest"
  suite=$("${PYTEST[@]}" 2>&1); rc=$?
  printf '%s\n' "$suite" | tail -n 1
  [ "$rc" = 0 ] && ok "suite green" || bad "test suite failed"
fi

# ── 2. Centrepiece ──────────────────────────────────────────────────────────
beat "2 · Crawl the broken-admin app and score against ground truth" \
     "6 pages, cycles (login↔register, dashboard↔admin…), 4 planted violations."
show "uv run python docs/demo_crawl.py"
uv run python docs/demo_crawl.py && ok "every planted violation found, nothing invented" \
  || bad "demo crawl did not match ground truth"

# ── 2b. Visual ──────────────────────────────────────────────────────────────
beat "2b · See it: the exploration graph in your browser" \
     "Pages as nodes, dashed orange = cycles kept, red = pages that violate policy."
show "uv run python -m apps.agent.orchestrator.demo_visual"
page=$(uv run python -m apps.agent.orchestrator.demo_visual) || bad "could not render the graph page"
if [ -n "${page:-}" ]; then
  echo "wrote $page"
  opener=""
  for c in xdg-open chromium google-chrome-stable firefox; do
    command -v "$c" >/dev/null && { opener=$c; break; }
  done
  if [ -n "$opener" ] && { [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; }; then
    nohup "$opener" "$page" >/dev/null 2>&1 &
    ok "opened in your browser ($opener)"
  else
    echo "no browser/display found — open this file manually: $page"
  fi
fi

# ── 3. Two implementations ──────────────────────────────────────────────────
beat "3 · Two implementations, one behaviour" \
     "Plain-Python reference loop and the LangGraph loop pass identical tests."
show "pytest test_explore.py -k dod -v"
dod=$(uv run pytest tests/unit/orchestrator/test_explore.py -k dod -o addopts="" -v --no-header -W ignore 2>&1)
rc=$?
printf '%s\n' "$dod" | grep -E "PASSED|FAILED|ERROR|passed|failed" | sed 's|^tests/unit/orchestrator/test_explore.py::||'
[ "$rc" = 0 ] && ok "reference and langgraph agree" || bad "DoD tests failed"

# ── 4. State machine ────────────────────────────────────────────────────────
beat "4 · The state machine, as Mermaid" "Paste into mermaid.live to render Scan → Reason → Act → Observe."
show "build_graph(...).get_graph().draw_mermaid()"
uv run python - <<'PY' || bad "could not render graph"
from apps.agent.orchestrator.config import OrchestratorConfig
from apps.agent.orchestrator.deps import fake_ports
from apps.agent.orchestrator.fakes import DEFAULT_POLICY
from apps.agent.orchestrator.graph_runner import build_graph

cfg = OrchestratorConfig(_env_file=None)  # type: ignore[call-arg]
print(build_graph(fake_ports(), DEFAULT_POLICY, cfg).get_graph().draw_mermaid())
PY

# ── 5. Guardrail ────────────────────────────────────────────────────────────
beat "5 · The guardrail: tooling enforces track ownership" \
     "A hook blocks writes outside the current track's folders."
show 'echo {Write apps/agent/crawler/x.py} | python3 .claude/hooks/track_b_paths.py'
printf '{"tool_name":"Write","tool_input":{"file_path":"apps/agent/crawler/x.py"},"cwd":"%s"}' "$PWD" \
  | python3 .claude/hooks/track_b_paths.py
rc=$?
[ "$rc" = 2 ] && ok "write blocked (exit=2)" || bad "hook returned exit=$rc, expected 2"

# ── 6. CI-shaped output ─────────────────────────────────────────────────────
beat "6 · CI-shaped output" "JSON report on stdout, structured logs on stderr, exit 1 when violations exist."
show "uv run python -m apps.agent.skeleton --fake --run-id demo"
errf=$(mktemp)
out=$(uv run python -m apps.agent.skeleton --fake --run-id demo 2>"$errf")
rc=$?
printf '%s\n' "$out" | head -n 14
printf '%s  …%s\n' "$D" "$X"
printf '%sstderr (first 2 log lines):%s\n' "$D" "$X"
head -n 2 "$errf" | cut -c1-170
rm -f "$errf"
[ "$rc" = 1 ] && ok "exit=1 — violation found, build would fail" || bad "expected exit=1, got $rc"

# ── 7. Dynamic sites ────────────────────────────────────────────────────────
if [ "$QUICK" = 0 ]; then
  beat "7 · Dynamic sites (experimental, opt-in)" \
       "Rotating ads, live counters, 70/30 outcomes, flaky elements — seeded simulation."
  show "uv run pytest tests/integration/orchestrator/test_dynamic_app.py"
  dyn=$("${PYTEST[@]}" tests/integration/orchestrator/test_dynamic_app.py 2>&1); rc=$?
  printf '%s\n' "$dyn" | tail -n 1
  [ "$rc" = 0 ] && ok "dynamic-state model behaves as specified" || bad "dynamic-app tests failed"
fi

# ── Wrap up ─────────────────────────────────────────────────────────────────
printf '\n%s━━ Done ━━%s\n' "$B$C" "$X"
if [ "$FAILED" = 0 ]; then
  printf '%sAll demo beats passed.%s\n' "$G" "$X"
else
  printf '%sOne or more beats failed — scroll up for ✘.%s\n' "$R" "$X"
fi
exit "$FAILED"
