"""The demo's business: Acme Mobile, Acme Bank... (DEMO_VERTICAL in demo.env).

Each one is a folder under verticals/:
  vertical.json  its brand, the assistant's persona, its customer, and the
                 wording the gateway's policies need (allowed topics, routing
                 rules, personal data patterns, tools, thresholds);
  catalogue.md   the products the assistant quotes;
  cards.json     optional: the cards and rows it words its own way, by id.
showcases.json refers to its values as {v:path}. The provisioning and the
chatbot both read it here.
"""
import json
import re

from target import ROOT, setting

VERTICAL_ID = setting("DEMO_VERTICAL", "mobile")
FOLDER = ROOT / "verticals" / VERTICAL_ID


def vertical() -> dict:
    """verticals/<DEMO_VERTICAL>/vertical.json, read on each call so an edit
    applies at once."""
    path = FOLDER / "vertical.json"
    if not path.exists():
        raise SystemExit(f"DEMO_VERTICAL={VERTICAL_ID}: no {path.relative_to(ROOT)}")
    return json.loads(path.read_text())


def policy(name: str):
    """One policy's domain values, from the vertical's "policies"."""
    return vertical()["policies"][name]


def catalogue_path() -> str:
    """The catalogue appended to the assistant's prompt, "" if none."""
    name = vertical()["assistant"].get("catalogue") or ""
    return str(FOLDER / name) if name else ""


PLACEHOLDER = re.compile(r"\{v:([A-Za-z0-9_.]+)\}")


def _lookup(data: dict, path: str):
    value = data
    for key in path.split("."):
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def _fill(value, data: dict):
    """{v:a.b} in a card replaced with the business's value at a.b: any value
    when it is the whole string (a list of tools, a number), else its text."""
    if isinstance(value, dict):
        return {k: _fill(v, data) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, data) for v in value]
    if isinstance(value, str):
        whole = PLACEHOLDER.fullmatch(value)
        if whole:
            return _lookup(data, whole[1])
        return PLACEHOLDER.sub(lambda m: str(_lookup(data, m[1])), value)
    return value


def _merge(base, extra):
    """extra laid over base: objects merge key by key, anything else replaces."""
    if isinstance(base, dict) and isinstance(extra, dict):
        return {**base, **{k: _merge(base.get(k), v) for k, v in extra.items()}}
    return extra


def for_business(registry: dict) -> dict:
    """showcases.json ({"groups", "showcases"}) set for the business: its
    cards.json laid over the cards and groups it rewords, by id, then every
    {v:...} filled in from its vertical.json."""
    path = FOLDER / "cards.json"
    extra = json.loads(path.read_text()) if path.exists() else {}
    for kind in ("groups", "showcases"):
        own = extra.get(kind) or {}
        registry[kind] = [_merge(item, own[item["id"]]) if item.get("id") in own else item
                          for item in registry.get(kind) or []]
    return _fill(registry, vertical())
