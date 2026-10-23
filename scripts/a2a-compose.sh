#!/usr/bin/env bash
# Runs docker compose for the A2A Gateway page's gateway (a2a/): the main
# gateway's definition and settings, with a2a/docker-compose.yaml on top, as a
# project of its own, its ports one above the main gateway's.
#
# Usage: ./scripts/a2a-compose.sh <docker compose arguments>

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/tools.sh"
load_demo_env "$ROOT"
export_gateway_ports "$ROOT"

A2A_GATEWAY_HTTPS_PORT=$((GATEWAY_HTTPS_PORT + 1)) \
A2A_GATEWAY_CONTROLLER_REST_PORT=$((GATEWAY_CONTROLLER_REST_PORT + 1)) \
  exec "$ROOT/scripts/gateway-compose.sh" -p "$DEMO_NAME-a2a-gateway" \
    -f docker-compose.yaml -f docker-compose.override.yaml -f ../a2a/docker-compose.yaml "$@"
