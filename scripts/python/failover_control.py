#!/usr/bin/env python3
"""Drives model-failover's live fault-injection step -- a different concern
from provision_showcases.py's one-time provisioning, though it reuses the
same Platform API client (platform_api.py): this toggles a provider's
upstream back and forth, repeatedly, during a live demo, while provisioning
brings an environment up once (idempotently) and is done.

Usage (see scripts/failover_demo.sh for the usual entrypoint):
    ./scripts/python/failover_control.py break [provider]    # the provider's large model now fails
    ./scripts/python/failover_control.py heal [provider]     # back to passthrough
    ./scripts/python/failover_control.py restore [provider]  # the provider back on its real API
    ./scripts/python/failover_control.py inject [provider]   # only route the provider through the mock
    # provider defaults to anthropic; must have a mock entry in FAULT_PROXY_PORTS
    # and in scripts/python/mocks/llm_fault_proxy.py's own PROVIDER_DEFAULTS.

break does the setup itself: it starts the fault mock if it is not running
(it then keeps running in the background, its log in .logs/) and routes the
provider through it if that is not done yet. restore undoes both.
"""
import os
import signal
import subprocess
import sys
import time

from platform_api import ROOT, PROVIDERS, read_secret, login, api, upsert_shared_provider, deploy, request, showcase
from target import LLM_GATEWAY

# Ports must agree with scripts/python/mocks/llm_fault_proxy.py's own DEFAULT_PORTS.
FAULT_PROXY_PORTS = {"anthropic": 8602, "mistral": 8603, "gemini": 8604}
MOCK = ROOT / "scripts" / "python" / "mocks" / "llm_fault_proxy.py"
LOGS = ROOT / ".logs"


def _fault_provider(provider_id: str) -> dict:
    if provider_id not in FAULT_PROXY_PORTS:
        sys.exit(f"no fault-injection mock for provider {provider_id!r} -- known: {sorted(FAULT_PROXY_PORTS)}")
    # FAULT_PROXY_PORTS and PROVIDERS (providers.json, filtered to enabled
    # ones) are two independently-maintained lists -- a provider named in one
    # but disabled (or removed) in the other needs its own clear error, not
    # next()'s bare StopIteration.
    provider = next((p for p in PROVIDERS if p["id"] == provider_id), None)
    if provider is None:
        sys.exit(f"{provider_id!r} has a fault-injection mock configured but isn't an enabled "
                  f"provider in providers.json -- known enabled providers: {[p['id'] for p in PROVIDERS]}")
    # Breaking a model where the failover card cannot run shows nothing, and
    # still fails every other card that uses that model.
    if provider_id in (showcase("model-failover").get("unsupportedProviders") or []):
        sys.exit(f"the Model failover card cannot run on {provider_id}: nothing to break there")
    return provider


def _mock_url(provider_id: str) -> str:
    """The mock's address as the gateway containers reach it."""
    return f"http://host.docker.internal:{FAULT_PROXY_PORTS[provider_id]}"


def _pid_file(provider_id: str):
    return LOGS / f"fault-proxy-{provider_id}.pid"


def _mock_running(provider_id: str) -> bool:
    status, _ = request("POST", f"http://localhost:{FAULT_PROXY_PORTS[provider_id]}/__control__/status", {})
    return status == 200


def _control(provider_id: str, path: str, data=None):
    """POST to the mock's own control endpoint, through platform_api's
    request() -- the same hardened client used for the Platform API itself,
    so a mock that isn't running fails with the same clean (0, {...}) this
    codebase handles everywhere else, not a raw urllib traceback."""
    url = f"http://localhost:{FAULT_PROXY_PORTS[provider_id]}/__control__/{path}"
    status, resp = request("POST", url, data if data is not None else {})
    if status != 200:
        sys.exit(f"  mock not reachable at {url} ({status}: {resp})")
    return resp


def _start_mock(provider_id: str):
    """Starts the provider's fault mock in the background, unless it already
    runs. It outlives this script, until restore stops it."""
    if _mock_running(provider_id):
        return
    LOGS.mkdir(exist_ok=True)
    log = open(LOGS / f"fault-proxy-{provider_id}.log", "a")
    proc = subprocess.Popen([sys.executable, "-u", str(MOCK), "--provider", provider_id,
                             "--port", str(FAULT_PROXY_PORTS[provider_id])],
                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)
    _pid_file(provider_id).write_text(str(proc.pid))
    for _ in range(40):
        if _mock_running(provider_id):
            print(f"  fault mock started on port {FAULT_PROXY_PORTS[provider_id]} "
                  f"(log: .logs/fault-proxy-{provider_id}.log)")
            return
        if proc.poll() is not None:
            break
        time.sleep(0.25)
    sys.exit(f"  the fault mock did not start: see .logs/fault-proxy-{provider_id}.log")


def _stop_mock(provider_id: str):
    """Stops the fault mock that break started, if it still runs. The PID is
    checked first: after a reboot, the file can name another process."""
    pid_file = _pid_file(provider_id)
    if not pid_file.exists():
        if _mock_running(provider_id):
            print(f"  a fault mock still runs on port {FAULT_PROXY_PORTS[provider_id]}, "
                  f"started by hand: stop it yourself")
        return
    pid = pid_file.read_text().strip()
    command = subprocess.run(["ps", "-p", pid, "-o", "command="], capture_output=True, text=True).stdout
    if pid.isdigit() and MOCK.name in command:
        os.kill(int(pid), signal.SIGTERM)
        print("  fault mock stopped")
    pid_file.unlink()


def _routed_through_mock(provider: dict) -> bool:
    status, resp = api("GET", f"/llm-providers/{provider['providerId']}")
    url = (((resp or {}).get("upstream") or {}).get("main") or {}).get("url") if status == 200 else None
    return url == _mock_url(provider["id"])


def inject(provider_id: str):
    provider = _fault_provider(provider_id)
    # Started BEFORE touching the gateway: this upstream is shared by every
    # lane on this provider, not just model-failover, so pointing it at a
    # mock that isn't running orphans all of them until someone notices and
    # runs restore.
    _start_mock(provider_id)
    secret = read_secret(provider)
    mock = dict(provider, upstreamUrl=_mock_url(provider_id))
    login()
    upsert_shared_provider(mock, secret)
    deploy(LLM_GATEWAY, "llm-providers", mock["providerId"], mock["providerContext"], mock["messagesSuffix"])
    print(f"  {provider['displayName']} upstream now {mock['upstreamUrl']}")
    # The gateway takes a few seconds to switch (about 3 s measured): without
    # this wait, the first question after break can still reach the real model.
    time.sleep(5)


def break_(provider_id: str):
    provider = _fault_provider(provider_id)
    _start_mock(provider_id)
    login()
    if not _routed_through_mock(provider):
        inject(provider_id)
    model = provider["models"]["large"]
    resp = _control(provider_id, "break", {"model": model})
    print(f"  {resp}  (model: {model})")


def heal(provider_id: str):
    _fault_provider(provider_id)  # validates provider_id, result unused
    if not _mock_running(provider_id):
        sys.exit(f"  no fault mock runs for {provider_id}: nothing to heal")
    resp = _control(provider_id, "heal")
    print(f"  {resp}")


def restore(provider_id: str):
    provider = _fault_provider(provider_id)
    secret = read_secret(provider)
    login()
    upsert_shared_provider(provider, secret)
    deploy(LLM_GATEWAY, "llm-providers", provider["providerId"], provider["providerContext"],
           provider["messagesSuffix"])
    print(f"  {provider['displayName']} upstream restored to {provider['upstreamUrl']}")
    # The gateway takes a few seconds to switch back (about 3 s measured) and
    # sends to the mock meanwhile: stopping it at once fails those requests.
    if _pid_file(provider_id).exists():
        print("  stopping the fault mock in 10 s, once the gateway has switched back")
        time.sleep(10)
        # A break run meanwhile routed the provider through the mock again: keep it.
        if _routed_through_mock(provider):
            print("  a break routed the provider through the mock again: the mock keeps running")
            return
    _stop_mock(provider_id)


MODES = {"inject": inject, "break": break_, "heal": heal, "restore": restore}


def main():
    if not sys.argv[1:] or sys.argv[1] not in MODES:
        sys.exit(f"usage: {sys.argv[0]} {{{'|'.join(MODES)}}} [provider=anthropic]")
    # The mock runs on this machine: a gateway elsewhere could not reach it, and
    # every card of that provider would fail there.
    if not LLM_GATEWAY.local:
        sys.exit("fault injection needs this machine's gateway: demo.env points to a remote one")
    provider_id = sys.argv[2] if len(sys.argv) > 2 else "anthropic"
    MODES[sys.argv[1]](provider_id)


if __name__ == "__main__":
    main()
