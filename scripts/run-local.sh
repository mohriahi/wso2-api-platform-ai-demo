#!/usr/bin/env bash
# Starts the demo on this machine: the MCP servers, AI Workspace, the AI
# Gateway and the chatbot. Data is kept between runs; to start from scratch,
# use reset-and-setup.sh instead.
#
# Steps (each one is marked "Step N" below and prints "### N/5" when it runs):
#   1. Read the settings: demo.env, and the external registry if it is on.
#   2. Start the MCP servers.
#   3. Start AI Workspace (the control plane).
#   4. Start the AI Gateway (the data plane).
#   5. Start the chatbot.
#   6. Set the gateway up again if the business (DEMO_VERTICAL) changed.
#
# Needs api-platform.env in ai-workspace/ and ai-gateway/ (reset-and-setup.sh
# creates them from their .example) and ai-chatbot/config.env.
#
# The gateway uses the same ports, image and config here and on the VM (see
# ai-gateway/.env). Compose also loads each docker-compose.override.yaml.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/tools.sh"

# Each container's output goes to a log file here, not to the terminal.
LOGS="$ROOT/.logs"

# ==== Step 1/6: read the settings =============================================
echo "### 1/6 settings"
load_demo_env "$ROOT"   # this machine's settings, created on the first run (see tools.sh)
resolve_python   # the Python 3 to use (see tools.sh)
resolve_analytics "$ROOT"   # says in the terminal when analytics stay off (see tools.sh)
use_external_registry "$ROOT"   # registry images, if secrets/registry.env turns them on
# The gateway's ports, moved up by the port offset from demo.env (see tools.sh).
export_gateway_ports "$ROOT"
require_env "$ROOT/ai-workspace/api-platform.env"
require_env "$ROOT/ai-gateway/api-platform.env"
require_env "$ROOT/ai-chatbot/config.env"

# ==== Step 2/6: MCP servers ===================================================
echo "### 2/6 mcp-servers"
# The MCP servers' network, shared with the gateway and AI Workspace (see the
# two docker-compose.override.yaml files).
docker network inspect "$DEMO_NAME-mcp" >/dev/null 2>&1 || docker network create "$DEMO_NAME-mcp" >/dev/null
# Recreated on every run, so the current version of their code is the one running.
(cd "$ROOT/mcp-servers" && docker compose up -d --force-recreate --remove-orphans) >"$LOGS/mcp-servers.log" 2>&1
# The A2A Gateway page's own gateway and agent, when that page is on
# (A2A_ENABLED in demo.env).
if [[ "${A2A_ENABLED:-false}" == true ]]; then
  "$ROOT/scripts/a2a-compose.sh" up -d --build --remove-orphans >"$LOGS/a2a.log" 2>&1
  # The agents are restarted on every run too, so they speak for the
  # current business.
  "$ROOT/scripts/a2a-compose.sh" up -d --force-recreate --no-deps acme-agent partner-agent >>"$LOGS/a2a.log" 2>&1
else
  "$ROOT/scripts/a2a-compose.sh" down >"$LOGS/a2a.log" 2>&1
fi

# ==== Step 3/6: AI Workspace (control plane) ==================================
echo "### 3/6 ai-workspace"
(cd "$ROOT/ai-workspace" && docker compose up -d --wait) >"$LOGS/ai-workspace.log" 2>&1

# ==== Step 4/6: AI Gateway (data plane) =======================================
echo "### 4/6 ai-gateway"
"$ROOT/scripts/gateway-compose.sh" up -d >"$LOGS/ai-gateway.log" 2>&1

# ==== Step 5/6: chatbot =======================================================
echo "### 5/6 ai-chatbot"
# Stops the previous chatbot first, or it would keep the port and the new one
# could not start.
"$ROOT/scripts/stop-ai-chatbot.sh"
(cd "$ROOT/ai-chatbot" && nohup "$PYTHON" server.py >"$LOGS/ai-chatbot.log" 2>&1 &)

# ==== Step 6/6: the business ==================================================
# The cards, the gateway's rules and the MCP and A2A backends depend on the
# business the demo plays (DEMO_VERTICAL). After a change, the gateway is set up
# again for it: a few minutes, once.
echo "### 6/6 business: ${DEMO_VERTICAL:-telco}"
if [[ "$(cat "$ROOT/verticals/.provisioned" 2>/dev/null)" != "${DEMO_VERTICAL:-telco}" ]]; then
  echo "  the gateway is not set up for it yet: provisioning (log: $LOGS/provisioning.log)"
  "$PYTHON" "$ROOT/scripts/python/provision_showcases.py" >"$LOGS/provisioning.log" 2>&1
fi

echo
echo "done. Everything is up:"
echo "  ai-workspace (control plane) : https://localhost:${AI_WORKSPACE_PORT}"
echo "  api-portal (not used)        : https://localhost:${API_PORTAL_PORT}"
echo "  platform-api                 : https://localhost:${PLATFORM_API_PORT}"
echo "  ai-gateway (data plane)      : https://localhost:${GATEWAY_HTTPS_PORT}"
echo "  ai-chatbot                   : http://localhost:${AI_CHATBOT_PORT}"
echo
echo "logs: $LOGS/{ai-workspace,ai-gateway,ai-chatbot}.log"
echo "stop everything: ./scripts/stop-local.sh"
