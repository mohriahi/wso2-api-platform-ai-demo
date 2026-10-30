#!/usr/bin/env python3
"""Turns the gateway's runtime log, read on stdin, into the audit record the
log-message policy keeps, in time order: each question and answer of an LLM
card, each tool call of an MCP card and its result. Used by
scripts/audit-log.sh."""
import json
import re
import sys

LINE = re.compile(r'time=(\S+) .*?msg="(.*)"\s*$')


def question(payload: dict) -> str:
    """The last thing the customer said, whatever the wire format."""
    messages = payload.get("messages") or payload.get("contents") or []
    for message in reversed(messages):
        if message.get("role") in ("user", None):
            content = message.get("content")
            if isinstance(content, str):
                return content
            parts = message.get("parts") or content or []
            return " ".join(p.get("text", "") for p in parts if isinstance(p, dict))
    return ""


def answer(payload: dict) -> str:
    if payload.get("content"):                                    # Anthropic
        return " ".join(b.get("text", "") for b in payload["content"] if isinstance(b, dict))
    if payload.get("choices"):                                    # OpenAI format (Mistral)
        return (payload["choices"][0].get("message") or {}).get("content") or ""
    if payload.get("candidates"):                                 # Gemini
        parts = (payload["candidates"][0].get("content") or {}).get("parts") or []
        return " ".join(p.get("text", "") for p in parts)
    return json.dumps(payload)[:200]


def tokens(payload: dict) -> str:
    usage = payload.get("usage") or payload.get("usageMetadata") or {}
    used_in = usage.get("input_tokens") or usage.get("prompt_tokens") or usage.get("promptTokenCount")
    used_out = usage.get("output_tokens") or usage.get("completion_tokens") or usage.get("candidatesTokenCount")
    return f"  [tokens in {used_in}, out {used_out}]" if used_in or used_out else ""


def load(text: str):
    """A logged payload: JSON, or an event stream whose last data line is."""
    try:
        return json.loads(text)
    except ValueError:
        data = [line[5:] for line in text.splitlines() if line.startswith("data:")]
        try:
            return json.loads(data[-1]) if data else None
        except ValueError:
            return None


def rpc(payload: dict, flow: str):
    """(what, text) for an MCP message, None for the protocol's own plumbing
    (initialize, notifications)."""
    method, params = payload.get("method"), payload.get("params") or {}
    if flow == "REQUEST":
        if method == "tools/call":
            return "tool call", "%s(%s)" % (params.get("name"), json.dumps(params.get("arguments") or {}))
        if method == "tools/list":
            return "tool list", "the agent asks which tools it may use"
        return None
    if payload.get("error"):
        return "error", str(payload["error"].get("message", payload["error"]))
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    if "tools" in result:
        return "tools offered", ", ".join(t.get("name", "?") for t in result["tools"])
    if "content" in result:
        return "tool result", " ".join(c.get("text", "") for c in result["content"] if isinstance(c, dict))
    return None


def short(text: str, width: int = 300) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width] + "..."


entries = []
for line in sys.stdin:
    match = LINE.search(line)
    if not match or "mediation-flow" not in match.group(2):
        continue
    try:
        record = json.loads(json.loads('"' + match.group(2) + '"'))
    except ValueError:
        continue
    payload = load(record["payload"]) if "payload" in record else None
    if not isinstance(payload, dict):    # the headers entry: the payload one follows
        continue
    when = match.group(1).replace("T", " ")[:23]
    lane = record.get("resource-path", "").split("/")[1] if record.get("resource-path") else "?"
    flow = record.get("mediation-flow")
    if "jsonrpc" in payload or "result" in payload or payload.get("method"):
        found = rpc(payload, flow)
        if found:
            entries.append((when, f"{when[:19]}  {lane}  {found[0]}", short(found[1])))
    elif flow == "REQUEST":
        entries.append((when, f"{when[:19]}  {lane}  question  (request {record.get('request-id', '?')[:8]})",
                        short(question(payload))))
    else:
        entries.append((when, f"{when[:19]}  {lane}  answer{tokens(payload)}", short(answer(payload))))

for _, head, text in sorted(entries, key=lambda e: e[0]):
    print(head)
    print(f"    {text}")

if not entries:
    print("No audit record yet: ask a question on one of the Audit log cards first.")
