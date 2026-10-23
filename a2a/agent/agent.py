"""The business's A2A agents, which the A2A showcases put behind the gateway.
What they say comes with the business the demo is set for
(verticals/<VERTICAL>/vertical.json, "a2a"): its own agent (ROLE=agent), or a
partner's (ROLE=partner), whose own card hides an instruction for the agents
that read it. Given a destination, each answers from a fixed table: no model
behind it, so every answer is the same on stage.

Built on the official A2A Python SDK, which serves the Agent Card and both
A2A bindings (JSON-RPC at /, HTTP+JSON under /) from one handler.
"""
import json
import os
import re

import uvicorn
from starlette.applications import Starlette

from a2a.helpers import get_message_text, new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes, create_rest_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill


def load():
    path = os.path.join(os.environ.get("VERTICALS", "/verticals"), os.environ.get("VERTICAL", "mobile"),
                        "vertical.json")
    with open(path) as handle:
        a2a = json.load(handle)["a2a"]
    return a2a["places"], a2a[os.environ.get("ROLE", "agent")]


PLACES, AGENT = load()


def answer(text):
    """The reply for the first place named in the text, by the group it is in."""
    replies = AGENT["replies"]
    for group, places in PLACES.items():
        for place in places:
            if re.search(r"\b%s\b" % re.escape(place), text, re.IGNORECASE) and group in replies:
                return replies[group].replace("{place}", place)
    if "elsewhere" in replies and re.search(r"\b(to|in|visit|visiting)\s+[A-Z]", text):
        return replies["elsewhere"]
    return replies["unknown"]


class Executor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue):
        text = get_message_text(context.message) if context.message else ""
        reply = answer(text)
        await event_queue.enqueue_event(new_text_message(reply, context_id=context.context_id))

    async def cancel(self, context: RequestContext, event_queue):
        return None


def build_app():
    url = os.environ.get("PUBLIC_URL", "http://acme-agent:8000")
    skill = AgentSkill(**AGENT["skill"])
    card = AgentCard(
        name=AGENT["name"],
        description=AGENT["description"],
        version="1.0.0",
        supported_interfaces=[
            AgentInterface(url=url, protocol_binding="JSONRPC", protocol_version="1.0"),
            AgentInterface(url=url, protocol_binding="HTTP+JSON", protocol_version="1.0"),
        ],
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[skill],
    )
    handler = DefaultRequestHandler(agent_executor=Executor(), task_store=InMemoryTaskStore(), agent_card=card)
    routes = create_agent_card_routes(card) + create_jsonrpc_routes(handler, "/") + create_rest_routes(handler)
    return Starlette(routes=routes)


if __name__ == "__main__":
    uvicorn.run(build_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
