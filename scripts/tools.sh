#!/usr/bin/env bash
# Shared helpers for the local-dev scripts in this directory. Source, don't
# execute:
#   source "$ROOT/scripts/tools.sh"
#
# deploy-certs-remote.sh does NOT source this file on purpose: it gets
# installed standalone on the VM (as a certbot renewal hook, see
# .claude/skills/_reference/tls-and-certs.md), with no sibling scripts/
# directory to find this file in.

# Resolves the Python 3 interpreter into $PYTHON. A `python3` shell alias is
# invisible to a non-interactive script, so this surfaces a clear error
# instead of a confusing "command not found". Falls back to bare `python`
# only after confirming it's actually Python 3.
resolve_python() {
  if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
  elif command -v python >/dev/null 2>&1 \
       && python -c 'import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)' 2>/dev/null; then
    PYTHON=python
  else
    echo "no Python 3 interpreter found (looked for python3, then python) -- install Python 3 first" >&2
    exit 1
  fi
}

# Creates a file from the .example next to it when it is missing, and says so.
# Usage: copy_example_if_missing <repo root> <path inside the repo>
copy_example_if_missing() {
  local root="$1" file="$2"
  if [[ ! -f "$root/$file" ]]; then
    cp "$root/$file.example" "$root/$file"
    echo "  created $file from $file.example"
  fi
}

# Loads this machine's settings from demo.env. On the first run, demo.env is
# created from demo.env.example; later, any setting the example has gained is
# pointed out, so it can be added.
load_demo_env() {
  local root="$1" key
  copy_example_if_missing "$root" demo.env
  for key in $(grep -oE '^[A-Z_]+=' "$root/demo.env.example" | tr -d '='); do
    grep -q "^$key=" "$root/demo.env" \
      || echo "  demo.env has no $key: add it from demo.env.example ($(grep "^$key=" "$root/demo.env.example"))" >&2
  done
  set -a
  source "$root/demo.env"
  set +a
}

# Moves every gateway port up by the port offset from demo.env (1 turns 8443
# into 8444) and hands the result to Docker Compose.
export_gateway_ports() {
  local root="$1" offset="${GATEWAY_PORT_OFFSET:-0}" name base
  while IFS='=' read -r name base; do
    export "$name=$((base + offset))"
  done < <(grep -E '^GATEWAY_[A-Z_]+_PORT=[0-9]+$' "$root/ai-gateway/.env")
}

# Turns demo.env's ANALYTICS_MODE plus secrets/api-keys.env's Moesif id into
# $ANALYTICS_ENABLED / $ANALYTICS_MOESIF_ID / $ANALYTICS_COMPOSE_PROFILES.
# Pass these as a command-scoped prefix on the one docker compose call that
# needs them (see gateway-compose.sh) -- not exported globally, since
# COMPOSE_PROFILES means something different to ai-workspace's own compose
# call and would otherwise leak into it.
resolve_analytics() {
  local root="$1"
  ANALYTICS_MOESIF_ID="$(sed -n 's/^APIP_GW_ANALYTICS_PUBLISHERS_MOESIF_APPLICATION_ID=//p' \
    "$root/secrets/api-keys.env" 2>/dev/null | tail -1)"
  case "${ANALYTICS_MODE:-moesif}" in
    moesif)
      # enabled=true with a blank id isn't a harmless no-op -- policy-engine's
      # config validation rejects it and the container refuses to start.
      if [[ -n "$ANALYTICS_MOESIF_ID" ]]; then
        ANALYTICS_ENABLED=true
        ANALYTICS_COMPOSE_PROFILES="moesif"   # the collector sending traces to Moesif
      else
        ANALYTICS_ENABLED=false
        ANALYTICS_COMPOSE_PROFILES=""
        echo "  analytics: ANALYTICS_MODE=moesif but secrets/api-keys.env has no" \
             "APIP_GW_ANALYTICS_PUBLISHERS_MOESIF_APPLICATION_ID -- leaving analytics off" \
             "(set ANALYTICS_MODE=local instead for the local observability stack)" >&2
      fi
      ;;
    local)
      ANALYTICS_ENABLED=false
      ANALYTICS_COMPOSE_PROFILES="tracing,logging,metrics"
      ;;
    *)
      echo "demo.env: ANALYTICS_MODE must be 'moesif' or 'local', got '$ANALYTICS_MODE'" >&2
      exit 1
      ;;
  esac
}

# The gateway's own keys, from secrets/api-keys.env: the embeddings
# provider's (EMBEDDINGS_PROVIDER_API_KEY, for the semantic cards) and
# Intelligent routing's classifier's (CLASSIFIER_API_KEY), each
# MISTRAL_API_KEY when blank. A key already in the environment wins. Sets
# $EMBEDDING_PROVIDER_API_KEY and $CLASSIFIER_API_KEY, which gateway-compose.sh
# hands to the gateway.
resolve_gateway_keys() {
  local root="$1"
  secret() { sed -n "s/^$1=//p" "$root/secrets/api-keys.env" 2>/dev/null | tail -1; }
  EMBEDDING_PROVIDER_API_KEY="${EMBEDDINGS_PROVIDER_API_KEY:-$(secret EMBEDDINGS_PROVIDER_API_KEY)}"
  EMBEDDING_PROVIDER_API_KEY="${EMBEDDING_PROVIDER_API_KEY:-$(secret MISTRAL_API_KEY)}"
  CLASSIFIER_API_KEY="${CLASSIFIER_API_KEY:-$(secret CLASSIFIER_API_KEY)}"
  CLASSIFIER_API_KEY="${CLASSIFIER_API_KEY:-$(secret MISTRAL_API_KEY)}"
}

# When secrets/registry.env has USE_EXTERNAL_REGISTRY=true, exports the newest
# product images of that registry, for docker compose and the gateway build.
# Otherwise nothing is exported and the public images are used.
use_external_registry() {
  local root="$1" images line
  images="$("$PYTHON" "$root/scripts/python/registry_images.py")" || exit 1
  while IFS= read -r line; do
    if [[ -n "$line" ]]; then
      export "$line"
      echo "  ${line#*=}"
    fi
  done <<< "$images"
}

require_env() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "Missing $file — copy it from ${file}.example and fill in real values first." >&2
    exit 1
  fi
}

gen_selfsigned() {
  local dir="$1" cert="$2" key="$3"
  if [[ -f "$dir/$cert" && -f "$dir/$key" ]]; then
    echo "  skip $dir/$cert (exists)"
    return
  fi
  mkdir -p "$dir"
  openssl req -x509 -newkey rsa:2048 -sha256 -days 825 -nodes \
    -keyout "$dir/$key" -out "$dir/$cert" \
    -subj "/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
  chmod 600 "$dir/$key"
  echo "  generated $dir/$cert + $key"
}

# Expects a global `pids` array of background job PIDs in the caller, e.g.:
#   pids=(); trap cleanup_pids EXIT INT TERM
cleanup_pids() {
  if ((${#pids[@]})); then
    kill "${pids[@]}" 2>/dev/null
  fi
}
