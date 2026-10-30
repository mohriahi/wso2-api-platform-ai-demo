#!/usr/bin/env bash
# Shows the gateway's audit record for the two Audit log cards (LLM and MCP),
# in time order: each question and answer, each tool call and its result, as
# the log-message policy wrote them. The API key and other credentials are
# never in it.
#
# Usage: ./scripts/audit-log.sh [how far back, default 30m]

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/tools.sh"
load_demo_env "$ROOT"
resolve_python

"$ROOT/scripts/gateway-compose.sh" logs --no-log-prefix --since "${1:-30m}" gateway-runtime 2>/dev/null \
  | "$PYTHON" "$ROOT/scripts/python/audit_log.py"
