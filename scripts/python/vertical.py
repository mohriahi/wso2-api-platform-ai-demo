"""The business the demo plays (DEMO_VERTICAL in demo.env): telco for Acme
Mobile, bank for Acme Bank. Each one is a folder of verticals/:
  vertical.json  its brand, assistant, customer, tools and agents, and the
                 words the gateway's policies use;
  catalogue.md   the products the assistant talks about;
  cards.json     how its cards are worded, when they differ from the default.
The provisioning and the chatbot both read it from here.
"""
import json
import re

from target import ROOT, setting

VERTICAL_ID = setting("DEMO_VERTICAL", "telco")
FOLDER = ROOT / "verticals" / VERTICAL_ID
# Each business has its own project in AI Workspace.
PROJECT_ID = VERTICAL_ID
# The businesses the gateway is already set up for, one per line: run-local.sh
# sets up a business only the first time it is chosen.
PROVISIONED = ROOT / "verticals" / ".set-up"


def own_id(name: str) -> str:
    """A resource's id in AI Workspace and on the gateways: each business has its own."""
    return f"{VERTICAL_ID}-{name}"


def own_path(context: str) -> str:
    """A route's path on the gateways, under the business's name, so the routes
    of every business live side by side."""
    return f"/{VERTICAL_ID}{context}"


def vertical() -> dict:
    """The business's vertical.json, read each time so an edit shows at once."""
    path = FOLDER / "vertical.json"
    if not path.exists():
        raise SystemExit(f"DEMO_VERTICAL={VERTICAL_ID}: no {path.relative_to(ROOT)}")
    return json.loads(path.read_text())


def policy(name: str):
    """The business's own words for one policy."""
    return vertical()["policies"][name]


def catalogue_path() -> str:
    """Where the business's catalogue is, "" if it has none."""
    name = vertical()["assistant"].get("catalogue") or ""
    return str(FOLDER / name) if name else ""


PLACEHOLDER = re.compile(r"\{v:([A-Za-z0-9_.]+)\}")


def _lookup(data: dict, path: str):
    value = data
    for key in path.split("."):
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def _text(value) -> str:
    """A value written inside a text (a list goes in as JSON)."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _fill(value, data: dict):
    """Each {v:a.b} in a card becomes the business's value at a.b."""
    if isinstance(value, dict):
        return {k: _fill(v, data) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, data) for v in value]
    if isinstance(value, str):
        whole = PLACEHOLDER.fullmatch(value)
        if whole:
            return _lookup(data, whole[1])
        return PLACEHOLDER.sub(lambda m: _text(_lookup(data, m[1])), value)
    return value


def _merge(base, extra):
    """extra over base: objects are combined, anything else is replaced."""
    if isinstance(base, dict) and isinstance(extra, dict):
        return {**base, **{k: _merge(base.get(k), v) for k, v in extra.items()}}
    return extra


def for_business(registry: dict) -> dict:
    """The cards of showcases.json, worded for the business: its cards.json on
    top, and its values in place of each {v:...}."""
    path = FOLDER / "cards.json"
    extra = json.loads(path.read_text()) if path.exists() else {}
    for kind in ("groups", "showcases"):
        own = extra.get(kind) or {}
        registry[kind] = [_merge(item, own[item["id"]]) if item.get("id") in own else item
                          for item in registry.get(kind) or []]
    return _fill(registry, dict(vertical(), id=VERTICAL_ID))
