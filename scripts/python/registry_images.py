#!/usr/bin/env python3
"""Finds which product images to run from the external registry set in
secrets/registry.env. For each product, it takes the newest update of the
version in demo.env (for 0.16.0, the newest 0.16.0.N) among the long-term
support (LTS) releases, else among the short-term support (STS) ones. When the
registry has neither, the product keeps its public image.

It only reads the registry's list of versions: Docker downloads the images
later, when it starts them. It prints one NAME=image line per image, and
nothing when USE_EXTERNAL_REGISTRY is not true.
"""
import base64
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request

from target import ROOT, DEMO_ENV, A2A_ENABLED, A2A_GATEWAY_VERSION, read_env_file

REGISTRY_FILE = ROOT / "secrets" / "registry.env"

# The gateway's three base images. They must be the same update.
GATEWAY = ["gateway-builder", "gateway-controller", "gateway-runtime"]
# Each product: its images and its version in demo.env.
PRODUCTS = [
    (["platform-api"], "PLATFORM_API_VERSION"),
    (["ai-workspace"], "AI_WORKSPACE_VERSION"),
    (["api-portal"], "API_PORTAL_VERSION"),
    (GATEWAY, "AI_GATEWAY_VERSION"),
]
# Where WSO2 keeps its STS releases, below the registry path.
STS_FOLDER = "sts"

# Some registries only answer clients that look like Docker.
USER_AGENT = "docker/27.3.1 (tag list)"


def http_get(url: str, auth: str = None):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if auth:
        headers["Authorization"] = auth
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"null"), resp.headers
    except urllib.error.HTTPError as err:
        return err.code, None, err.headers


def fetch_tags(host: str, repository: str, basic: str) -> list:
    """The list of versions (tags) of an image, empty when the registry does
    not have it."""
    status, _, headers = http_get(f"https://{host}/v2/")
    challenge = headers.get("WWW-Authenticate", "") if status == 401 else ""
    auth = basic
    if challenge.lower().startswith("bearer"):
        params = dict(re.findall(r'(\w+)="([^"]*)"', challenge))
        status, body, _ = http_get(f"{params['realm']}?service={params.get('service', '')}"
                                   f"&scope=repository:{repository}:pull", basic)
        if status != 200:
            return []
        auth = "Bearer " + (body.get("token") or body.get("access_token"))
    status, body, _ = http_get(f"https://{host}/v2/{repository}/tags/list", auth)
    if status != 200:
        return []
    return body.get("tags") or []


def updates(version: str, tags: list) -> list:
    """The update numbers of a version in the tags: 0.16.0.4 gives 4. Gives
    [-1] when only the version itself (0.16.0) is there."""
    found = [int(t.rsplit(".", 1)[1]) for t in tags if re.fullmatch(re.escape(version) + r"\.\d+", t)]
    return found or ([-1] if version in tags else [])


def tag(version: str, update: int) -> str:
    return version if update < 0 else f"{version}.{update}"


def find(host: str, path: str, basic: str, names: list, version: str) -> dict:
    """The images of a version, newest update first among the LTS releases,
    then among the STS ones. Empty when the registry has neither."""
    for base in (path, "/".join(filter(None, (path, STS_FOLDER)))):
        repository = lambda name: "/".join(filter(None, (base, name)))
        common = set.intersection(*(set(updates(version, fetch_tags(host, repository(name), basic)))
                                    for name in names))
        if common:
            return {name: f"{host}/{repository(name)}:{tag(version, max(common))}" for name in names}
    return {}


def main():
    conf = read_env_file(REGISTRY_FILE) if REGISTRY_FILE.exists() else {}
    if conf.get("USE_EXTERNAL_REGISTRY", "").lower() != "true":
        return
    url = conf.get("EXTERNAL_REGISTRY_URL", "").removeprefix("https://").rstrip("/")
    if not url:
        sys.exit(f"USE_EXTERNAL_REGISTRY is true but EXTERNAL_REGISTRY_URL is empty in {REGISTRY_FILE}")
    host, _, path = url.partition("/")
    username, token = conf.get("EXTERNAL_REGISTRY_USERNAME", ""), conf.get("EXTERNAL_REGISTRY_TOKEN", "")
    login = subprocess.run(["docker", "login", host, "-u", username, "--password-stdin"],
                           input=token, capture_output=True, text=True)
    if login.returncode != 0:
        sys.exit(f"docker login {host} failed: check the username and token in {REGISTRY_FILE}")
    basic = "Basic " + base64.b64encode(f"{username}:{token}".encode()).decode()

    # The A2A Gateway page runs a gateway of its own, at its own version.
    wanted = [("", names, DEMO_ENV[setting]) for names, setting in PRODUCTS]
    if A2A_ENABLED:
        wanted.append(("A2A_", GATEWAY, A2A_GATEWAY_VERSION))

    for prefix, names, version in wanted:
        images = find(host, path, basic, names, version)
        if not images:
            print(f"  {url}: no {names[-1]} {version}, the public image is used", file=sys.stderr)
        for name, image in images.items():
            print(f"{prefix}{name.upper().replace('-', '_')}_IMAGE={image}")


if __name__ == "__main__":
    main()
