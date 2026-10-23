"""The demo's business: Acme Mobile, Acme Bank... (DEMO_VERTICAL in demo.env).

Each one is a folder under verticals/: its brand, the assistant's persona and
catalogue, and the wording the gateway's policies need (allowed topics,
routing rules, personal data patterns, thresholds). The provisioning and the
chatbot both read it here.
"""
import json

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
