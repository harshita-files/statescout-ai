#!/usr/bin/env bash
# StateScout — local-site audit console.  Opens on http://127.0.0.1:8081
set -e
cd "$(dirname "$0")"

# GEMINI_API_KEY is OPTIONAL. With it, each crawled state also gets a Gemini
# vision pass. Without it, the audit still runs fully on the deterministic
# DOM/accessibility parse (the vision pass is just skipped).
if [ -z "${GEMINI_API_KEY:-}" ] && [ -f .env ]; then
  export GEMINI_API_KEY="$(grep -E '^GEMINI_API_KEY=' .env | head -1 | cut -d= -f2- | tr -d "\"' " | tr -d '\r\n')"
fi
if [ -z "${GEMINI_API_KEY:-}" ]; then
  echo "note: no GEMINI_API_KEY — running deterministic-only (vision pass skipped)."
fi

echo "Neo4j + Redis must be running:  docker compose -f infra/docker-compose.yml up -d"
echo "Opening  http://127.0.0.1:8081   (static file server uses :8090)"
exec uv run uvicorn scripts.local_audit_app:app --port 8081 --host 127.0.0.1
