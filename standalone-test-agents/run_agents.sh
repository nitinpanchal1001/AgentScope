#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY is required. Export it before starting the agents."
  exit 1
fi

if ! command -v uvicorn >/dev/null 2>&1; then
  echo "Install dependencies first: uv sync"
  exit 1
fi

pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

start_agent() {
  local module="$1"
  local port="$2"
  local name="$3"
  echo "Starting $name on http://127.0.0.1:$port"
  uvicorn "$module" --host 0.0.0.0 --port "$port" &
  pids+=("$!")
}

start_agent agents.faq.app:app 8101 "FAQ agent"
start_agent agents.research.app:app 8102 "Research agent"
start_agent agents.data_analyst.app:app 8103 "Data analyst agent"
start_agent agents.travel_planner.app:app 8104 "Travel planner agent"
start_agent agents.incident_triage.app:app 8105 "Incident triage agent"
start_agent agents.uiux_designer.app:app 8111 "UI/UX designer agent"
start_agent agents.frontend_developer.app:app 8112 "Frontend developer agent"
start_agent agents.backend_developer.app:app 8113 "Backend developer agent"
start_agent agents.qa_engineer.app:app 8114 "QA engineer agent"
start_agent agents.quality_specialist.app:app 8115 "Accessibility and performance agent"
start_agent agents.product_team.app:app 8116 "Coordinated product team"

wait

