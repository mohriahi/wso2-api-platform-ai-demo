#!/usr/bin/env python3
"""The MCP servers the MCP cards put behind the gateway, one per business at
/<business>/mcp. Their tools and data come from the "mcp" part of each
business's vertical.json:

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


def load(folder):
    """One business's server, from its vertical.json, or None if it has none."""
    path = os.path.join(folder, "vertical.json")
    if not os.path.exists(path):
        return None
    with open(path) as handle:
        business = json.load(handle)
    server = (business.get("mcp") or {}).get(os.environ.get("TOOLSET", "core"))
    if not server:
        return None

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
    server = fill(server)
    server["tools"] = {tool["name"]: tool for tool in server["tools"].values()}
    return server


# Every business, each at /<business>/mcp, so switching the demo's business
# needs no restart.
ROOT = os.environ.get("VERTICALS", "/verticals")
SERVERS = {name: server for name in sorted(os.listdir(ROOT))
           if (server := load(os.path.join(ROOT, name)))}

# Each MCP session starts from the same account, so a change made in one
# conversation never shows in another.
SESSIONS = {}  # Mcp-Session-Id -> (its server, the account in that session)
MAX_SESSIONS = 1000


def schema(server, tool):
    """The tool as tools/list shows it."""
    key, items = server["key"], server["items"]
    properties, required = {}, []
    if tool["does"] == "change":
        properties[key] = {"type": "string", "enum": list(items), "description": tool["argument"]}
        required = [key]
    elif tool["does"] == "order":
        properties[tool["argument"]] = {"type": "string", "description": tool["argumentDescription"]}
        required = [tool["argument"]]
    elif tool["does"] == "terms":
        properties[key] = {"type": "string", "description": tool["argument"]}
        required = [key]
    shape = {"type": "object", "properties": properties}
    if required:
        shape["required"] = required
    return {"name": tool["name"], "description": tool["description"], "inputSchema": shape}


def find(wanted, names):
    wanted = str(wanted or "").strip().lower()
    return next((n for n in names if n.lower() == wanted), None)


def call_tool(server, name, args, account):
    """(result, is_error) for one tools/call."""
    tool = server["tools"].get(name)
    if tool is None:
        return {"error": "unknown tool %r" % name}, True
    key, items = server["key"], server["items"]
    noun = server.get("noun", key)
    if tool["does"] == "list":
        if isinstance(items, dict):
            return [dict({key: item}, **details) for item, details in items.items()], False
        return items, False
    if tool["does"] == "account":
        own = items[account[key]]
        return dict(account, **{field: own[source] for field, source in tool.get("adds", {}).items()}), False
    if tool["does"] == "change":
        item = find(args.get(key), items)
        if item is None:
            return {"error": "unknown %s %r, expected one of %s" % (noun, args.get(key), list(items))}, True
        previous, account[key] = account[key], item
        label = key[:1].upper() + key[1:]
        return dict({"previous" + label: previous, "new" + label: item},
                    **{field: items[item][field] for field in tool.get("replies", [])}), False
    if tool["does"] == "order":
        address = str(args.get(tool["argument"], "")).strip()
        if not address:
            return {"error": "%s is required" % tool["argument"]}, True
        return dict({"ordered": True, tool["argument"]: address}, **tool.get("replies", {})), False
    if tool["does"] == "terms":
        item = find(args.get(key), server["terms"])
        if item is None:
            return {"error": "unknown %s %r, expected one of %s" % (noun, args.get(key), list(server["terms"]))}, True
        return {key: item, "terms": server["terms"][item]}, False
    return {"error": "tool %r does nothing this server knows" % name}, True


def handle(server, message, account):
    """The JSON-RPC reply to one request, in the session that owns account."""
    method, params, rid = message.get("method"), message.get("params") or {}, message.get("id")
    if method == "initialize":
        result = {"protocolVersion": params.get("protocolVersion") or "2025-06-18",
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": server["server"], "version": "1.0.0"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [schema(server, tool) for tool in server["tools"].values()]}
    elif method == "tools/call":
        output, is_error = call_tool(server, params.get("name"), params.get("arguments") or {}, account)
        print("%s tools/call %s %s -> %s" % (server["server"], params.get("name"),
                                            json.dumps(params.get("arguments") or {}),
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
        parts = self.path.split("?", 1)[0].strip("/").split("/")
        if len(parts) != 2 or parts[1] != "mcp" or parts[0] not in SERVERS:
            return self._reply(404, {"error": "not found: use POST /<business>/mcp"})
        server = SERVERS[parts[0]]
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
            SESSIONS[session] = (server, dict(server.get("account", {})))
            return self._reply(200, handle(server, message, SESSIONS[session][1]), session)
        # Every other request names its session, as the transport requires: a
        # missing one is a client error, an unknown one means initialize again.
        session = self.headers.get("mcp-session-id")
        if not session or session not in SESSIONS or SESSIONS[session][0] is not server:
            return self._reply(400 if not session else 404, {
                "jsonrpc": "2.0", "id": message.get("id"),
                "error": {"code": -32000, "message": "no session: send initialize first"}})
        if "id" not in message:  # a notification: acknowledged, never answered
            self.send_response(202)
            self.send_header("content-length", "0")
            self.end_headers()
            return
        self._reply(200, handle(server, message, SESSIONS[session][1]))

    def do_GET(self):
        # No server-to-client stream: everything this server says is a reply.
        self._reply(405, {"error": "use POST /<business>/mcp"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    for name, server in SERVERS.items():
        print("%s MCP server listening on :%d/%s/mcp" % (server["server"], port, name), flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
