#!/usr/bin/env python3
"""The MCP servers the MCP cards put behind the gateway. Their tools and data
come with the business the demo plays (the "mcp" part of its vertical.json):

- its own server (TOOLSET=core): the products, one signed-in customer, and
  tools to read the account, change it and order a replacement;
- a partner's server (TOOLSET=partner), with two hidden attacks: an
  instruction in a tool description (the Poisoned tool description card) and
  another in the terms a tool returns (the Tool result screening card).

It speaks MCP in its simplest form, with the Python standard library only, so
the stock Python image runs it as is.
"""
import json
import os
import re
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def load():
    """This server's part of the business, read once at start."""
    path = os.path.join(os.environ.get("VERTICALS", "/verticals"), os.environ.get("VERTICAL", "telco"),
                        "vertical.json")
    with open(path) as handle:
        business = json.load(handle)

    def fill(value):
        if isinstance(value, dict):
            return {k: fill(v) for k, v in value.items()}
        if isinstance(value, list):
            return [fill(v) for v in value]
        if isinstance(value, str):
            def look(match):
                found = business
                for key in match[1].split("."):
                    found = found[key]
                return str(found)
            return re.sub(r"\{v:([A-Za-z0-9_.]+)\}", look, value)
        return value
    return fill(business["mcp"][os.environ.get("TOOLSET", "core")])


SERVER = load()
KEY, ITEMS = SERVER["key"], SERVER["items"]
TOOLS = {tool["name"]: tool for tool in SERVER["tools"].values()}

# Each MCP session starts from the same account, so a change made in one
# conversation never shows in another.
SESSIONS = {}  # Mcp-Session-Id -> the account in that session
MAX_SESSIONS = 1000


def schema(tool):
    """The tool as tools/list shows it."""
    properties, required = {}, []
    if tool["does"] == "change":
        properties[KEY] = {"type": "string", "enum": list(ITEMS), "description": tool["argument"]}
        required = [KEY]
    elif tool["does"] == "order":
        properties[tool["argument"]] = {"type": "string", "description": tool["argumentDescription"]}
        required = [tool["argument"]]
    elif tool["does"] == "terms":
        properties[KEY] = {"type": "string", "description": tool["argument"]}
        required = [KEY]
    shape = {"type": "object", "properties": properties}
    if required:
        shape["required"] = required
    return {"name": tool["name"], "description": tool["description"], "inputSchema": shape}


def find(wanted, names):
    wanted = str(wanted or "").strip().lower()
    return next((n for n in names if n.lower() == wanted), None)


def call_tool(name, args, account):
    """(result, is_error) for one tools/call."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": "unknown tool %r" % name}, True
    noun = SERVER.get("noun", KEY)
    if tool["does"] == "list":
        if isinstance(ITEMS, dict):
            return [dict({KEY: item}, **details) for item, details in ITEMS.items()], False
        return ITEMS, False
    if tool["does"] == "account":
        own = ITEMS[account[KEY]]
        return dict(account, **{field: own[source] for field, source in tool.get("adds", {}).items()}), False
    if tool["does"] == "change":
        item = find(args.get(KEY), ITEMS)
        if item is None:
            return {"error": "unknown %s %r, expected one of %s" % (noun, args.get(KEY), list(ITEMS))}, True
        previous, account[KEY] = account[KEY], item
        label = KEY[:1].upper() + KEY[1:]
        return dict({"previous" + label: previous, "new" + label: item},
                    **{field: ITEMS[item][field] for field in tool.get("replies", [])}), False
    if tool["does"] == "order":
        address = str(args.get(tool["argument"], "")).strip()
        if not address:
            return {"error": "%s is required" % tool["argument"]}, True
        return dict({"ordered": True, tool["argument"]: address}, **tool.get("replies", {})), False
    if tool["does"] == "terms":
        item = find(args.get(KEY), SERVER["terms"])
        if item is None:
            return {"error": "unknown %s %r, expected one of %s" % (noun, args.get(KEY), list(SERVER["terms"]))}, True
        return {KEY: item, "terms": SERVER["terms"][item]}, False
    return {"error": "tool %r does nothing this server knows" % name}, True


def handle(message, account):
    """The JSON-RPC reply to one request, in the session that owns account."""
    method, params, rid = message.get("method"), message.get("params") or {}, message.get("id")
    if method == "initialize":
        result = {"protocolVersion": params.get("protocolVersion") or "2025-06-18",
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": SERVER["server"], "version": "1.0.0"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [schema(tool) for tool in TOOLS.values()]}
    elif method == "tools/call":
        output, is_error = call_tool(params.get("name"), params.get("arguments") or {}, account)
        print("tools/call %s %s -> %s" % (params.get("name"), json.dumps(params.get("arguments") or {}),
                                         "error" if is_error else "ok"), flush=True)
        result = {"content": [{"type": "text", "text": json.dumps(output, ensure_ascii=False)}], "isError": is_error}
    else:
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": "method not found: %s" % method}}
    return {"jsonrpc": "2.0", "id": rid, "result": result}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # tools/call lines above are the log worth reading

    def _reply(self, status, payload, session=None):
        body = json.dumps(payload).encode()
        self.send_response(status)
        if session:
            self.send_header("mcp-session-id", session)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/mcp":
            return self._reply(404, {"error": "not found"})
        try:
            length = int(self.headers.get("content-length") or 0)
            message = json.loads(self.rfile.read(max(length, 0)) or b"{}")
        except ValueError:
            return self._reply(400, {"jsonrpc": "2.0", "id": None,
                                     "error": {"code": -32700, "message": "parse error"}})
        if not isinstance(message, dict):
            return self._reply(400, {"jsonrpc": "2.0", "id": None,
                                     "error": {"code": -32600, "message": "expected one JSON-RPC object"}})
        if message.get("method") == "initialize":
            if len(SESSIONS) >= MAX_SESSIONS:
                SESSIONS.clear()
            session = uuid.uuid4().hex
            SESSIONS[session] = dict(SERVER.get("account", {}))
            return self._reply(200, handle(message, SESSIONS[session]), session)
        # Every other request names its session, as the transport requires: a
        # missing one is a client error, an unknown one means initialize again.
        session = self.headers.get("mcp-session-id")
        if not session or session not in SESSIONS:
            return self._reply(400 if not session else 404, {
                "jsonrpc": "2.0", "id": message.get("id"),
                "error": {"code": -32000, "message": "no session: send initialize first"}})
        if "id" not in message:  # a notification: acknowledged, never answered
            self.send_response(202)
            self.send_header("content-length", "0")
            self.end_headers()
            return
        self._reply(200, handle(message, SESSIONS[session]))

    def do_GET(self):
        # No server-to-client stream: everything this server says is a reply.
        self._reply(405, {"error": "use POST /mcp"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print("%s MCP server listening on :%d/mcp" % (SERVER["server"], port), flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
