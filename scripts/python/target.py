"""Where the demo runs: the AI Workspace and the gateways. The provisioning
and the chatbot both read them here.

By default, this machine's stack. The REMOTE_ settings in demo.env point to
one that runs elsewhere (see demo.env.example).
"""
import os
import sys
from collections import namedtuple
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def read_env_file(path: Path) -> dict:
    """Reads a KEY=VALUE file, such as demo.env or secrets/*.env."""
    conf = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            conf[key.strip()] = value.strip()
    return conf


def _read_demo_env() -> dict:
    """demo.env, with the example's value for any setting it lacks. Created
    from demo.env.example on the first run."""
    path, example = ROOT / "demo.env", ROOT / "demo.env.example"
    if not path.exists():
        if not example.exists():
            sys.exit(f"missing {example} -- run this from a checkout of the repo")
        path.write_text(example.read_text())
        print(f"  created {path.name} from {example.name} -- adapt it to this machine if needed")
    return {**read_env_file(example), **read_env_file(path)}


DEMO_ENV = _read_demo_env()

# The A2A Gateway page (A2A_ENABLED in demo.env) has a gateway of its own,
# started from a2a/ next to the main one: see a2a/docker-compose.yaml.
A2A_ENABLED = (os.environ.get("A2A_ENABLED") or DEMO_ENV.get("A2A_ENABLED", "false")) == "true"
A2A_GATEWAY_VERSION = os.environ.get("A2A_GATEWAY_VERSION") or DEMO_ENV.get("A2A_GATEWAY_VERSION", "")


def a2a_supported(card: dict) -> bool:
    """Whether this A2A card runs: the A2A Gateway page is on, and its gateway
    is recent enough. A card that needs a newer gateway than the first A2A one
    names that version in its a2a block ("gatewayVersion")."""
    def numbers(version: str) -> tuple:
        return tuple(int(n) for n in version.split(".") if n.isdigit())
    need = card["a2a"].get("gatewayVersion")
    return A2A_ENABLED and (not need or numbers(A2A_GATEWAY_VERSION) >= numbers(need))


def _raw(name: str) -> str:
    return os.environ.get(name) or DEMO_ENV.get(name) or ""


# The names the REMOTE_ settings had before, still read so a demo.env written
# with them keeps working. Only when it uses AIW_URL, their switch to an
# existing deployment, so this machine's stack never picks them up.
_LEGACY_NAMES = {
    "REMOTE_AI_WORKSPACE_URL": ("AIW_URL",),
    "REMOTE_ADMIN_USERNAME": ("ADMIN_USERNAME",),
    "REMOTE_ADMIN_PASSWORD": ("ADMIN_PASSWORD",),
    "REMOTE_GATEWAY_ID": ("GATEWAY_ID",),
    "REMOTE_GATEWAY_URL": ("GATEWAY_BASE", "GATEWAY_ENDPOINT"),
    "REMOTE_MCP_GATEWAY_ID": ("MCP_GATEWAY_ID",),
    "REMOTE_MCP_GATEWAY_URL": ("MCP_GATEWAY_BASE", "MCP_GATEWAY_ENDPOINT"),
}
_LEGACY = not _raw("REMOTE_AI_WORKSPACE_URL") and bool(_raw("AIW_URL"))


def setting(name: str, default: str = "") -> str:
    """A setting from the environment, else demo.env, else the default."""
    value = _raw(name)
    for old in (_LEGACY_NAMES.get(name, ()) if _LEGACY and not value else ()):
        value = _raw(old)
        if value:
            # *_ENDPOINT held a bare host:port, *_BASE a URL.
            value = "https://" + value if old.endswith("_ENDPOINT") else value
            break
    return value or default


def gateway_ports() -> dict:
    """This machine's gateway ports, plus GATEWAY_PORT_OFFSET."""
    offset = int(DEMO_ENV.get("GATEWAY_PORT_OFFSET") or 0)
    return {key: str(int(value) + offset)
            for key, value in read_env_file(ROOT / "ai-gateway" / ".env").items()
            if key.startswith("GATEWAY_") and key.endswith("_PORT") and value.isdigit()}


# A gateway: its id in AI Workspace, its URL, its management API (to check
# deployments without leaving traces in analytics; "" if unknown), and
# whether it is this machine's own.
Gateway = namedtuple("Gateway", "id url controller_url local")


def remote_gateway(prefix: str):
    """The gateway set by <prefix>_ID and <prefix>_URL, None if not set."""
    gateway_id, url = setting(f"{prefix}_ID"), setting(f"{prefix}_URL")
    if bool(gateway_id) != bool(url):
        sys.exit(f"{prefix}_ID and {prefix}_URL go together -- see demo.env.example")
    return Gateway(gateway_id, url.rstrip("/"), setting(f"{prefix}_CONTROLLER_URL").rstrip("/"), False) \
        if gateway_id else None


# This machine's stack, unless REMOTE_AI_WORKSPACE_URL points elsewhere.
REMOTE = bool(setting("REMOTE_AI_WORKSPACE_URL"))
_remote_llm = remote_gateway("REMOTE_GATEWAY")
if REMOTE != bool(_remote_llm):
    sys.exit("REMOTE_AI_WORKSPACE_URL, REMOTE_GATEWAY_ID and REMOTE_GATEWAY_URL go together -- see demo.env.example")

if REMOTE:
    WORKSPACE_URL = setting("REMOTE_AI_WORKSPACE_URL").rstrip("/")
    ADMIN_USERNAME = setting("REMOTE_ADMIN_USERNAME", "admin")
    # Never in demo.env: the environment only (ADMIN_PASSWORD with the old names).
    ADMIN_PASSWORD = os.environ.get("REMOTE_ADMIN_PASSWORD") or \
        (os.environ.get("ADMIN_PASSWORD", "") if _LEGACY else "")
    LLM_GATEWAY = _remote_llm
else:
    _ports = gateway_ports()
    WORKSPACE_URL = f"https://localhost:{DEMO_ENV['AI_WORKSPACE_PORT']}"
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")  # the one generate-local-certs.sh hashed
    LLM_GATEWAY = Gateway("local-gateway", f"https://localhost:{_ports['GATEWAY_HTTPS_PORT']}",
                          f"http://localhost:{_ports['GATEWAY_CONTROLLER_REST_PORT']}", True)

# The MCP cards can use another gateway, local stack or not.
MCP_GATEWAY = remote_gateway("REMOTE_MCP_GATEWAY") or LLM_GATEWAY

# The A2A cards' gateway, on this machine, its ports one above the main
# gateway's (scripts/a2a-compose.sh).
_ports = gateway_ports()
A2A_GATEWAY = Gateway("a2a-gateway", f"https://localhost:{int(_ports['GATEWAY_HTTPS_PORT']) + 1}",
                      f"http://localhost:{int(_ports['GATEWAY_CONTROLLER_REST_PORT']) + 1}", True)

