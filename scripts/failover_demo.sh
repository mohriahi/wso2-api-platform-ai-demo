#!/usr/bin/env bash
# Drives the model-failover showcase's fault-injection step, for whichever
# provider you're demoing (anthropic or mistral; anthropic by default).
#
# During the demo:
#   ./scripts/failover_demo.sh break     # the provider's large model now 503s; the first time,
#                                        # it starts the fault mock and routes the provider through it
#   ./scripts/failover_demo.sh heal      # passthrough restored
#
# Afterwards:
#   ./scripts/failover_demo.sh restore   # provider back on the real API, fault mock stopped
#
# Everything here just forwards to scripts/python/failover_control.py, which
# knows the provider list, the fault-proxy ports and each provider's own
# "large" model id -- there is nothing to type here but the provider name.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/tools.sh"
resolve_python   # sets $PYTHON -- python3, or a confirmed-Python-3 `python` (see tools.sh)

case "${1:-}" in
  inject|break|heal|restore) "$PYTHON" "$ROOT/scripts/python/failover_control.py" "$1" "${2:-anthropic}" ;;
  *)
    echo "usage: $0 {inject|break|heal|restore} [provider=anthropic]" >&2
    exit 1
    ;;
esac
