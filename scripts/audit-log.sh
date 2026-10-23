#!/usr/bin/env bash
# Shows the gateways' audit record for the three Audit log cards (LLM, MCP and
# A2A), in time order: each question and answer, each tool call and its result,
# each message to an agent and its answer, as the log-message policy wrote them.
# The API key and other credentials are never in it.
#
# Usage: ./scripts/audit-log.sh [how far back, default 30m]

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/tools.sh"
load_demo_env "$ROOT"
resolve_python

# The main gateway's record, and the A2A gateway's when the A2A page is on.
{
  "$ROOT/scripts/gateway-compose.sh" logs --no-log-prefix --since "${1:-30m}" gateway-runtime 2>/dev/null
  if [[ "${A2A_ENABLED:-false}" == true ]]; then
    "$ROOT/scripts/a2a-compose.sh" logs --no-log-prefix --since "${1:-30m}" gateway-runtime 2>/dev/null
  fi
} | "$PYTHON" "$ROOT/scripts/python/audit_log.py"
