"""The agents the A2A cards put behind the gateway, one per business at
/<business>. What they say comes from the "a2a" part of each business's
vertical.json: its own agent (ROLE=agent), or a partner's (ROLE=partner),
whose own card hides an instruction for the agents that read it.

Given a destination, each answers from a fixed table, with no model behind
it, so every answer is the same on stage. Built on the official A2A SDK.
"""
import json
import os
import re

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount

from a2a.helpers import get_message_text, new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes, create_rest_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill


def load(folder):
    """One business's agent (ROLE: agent or partner), or None if it has none."""
    path = os.path.join(folder, "vertical.json")
    if not os.path.exists(path):
        return None
    with open(path) as handle:
        a2a = json.load(handle).get("a2a") or {}
    agent = a2a.get(os.environ.get("ROLE", "agent"))
    return (a2a["places"], agent) if agent else None


def answer(places, agent, text):
    """The reply for the first place named in the message."""
    replies = agent["replies"]
    for group, names in places.items():
        for place in names:
            if re.search(r"\b%s\b" % re.escape(place), text, re.IGNORECASE) and group in replies:
                return replies[group].replace("{place}", place)
    if "elsewhere" in replies and re.search(r"\b(to|in|visit|visiting)\s+[A-Z]", text):
        return replies["elsewhere"]
    return replies["unknown"]


class Executor(AgentExecutor):
    def __init__(self, places, agent):
        self.places, self.agent = places, agent

    async def execute(self, context: RequestContext, event_queue):
        text = get_message_text(context.message) if context.message else ""
        reply = answer(self.places, self.agent, text)
        await event_queue.enqueue_event(new_text_message(reply, context_id=context.context_id))

    async def cancel(self, context: RequestContext, event_queue):
        return None


def build_app(places, agent, url):
    skill = AgentSkill(**agent["skill"])
    card = AgentCard(
        name=agent["name"],
        description=agent["description"],
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
    handler = DefaultRequestHandler(agent_executor=Executor(places, agent), task_store=InMemoryTaskStore(),
                                    agent_card=card)
    routes = create_agent_card_routes(card) + create_jsonrpc_routes(handler, "/") + create_rest_routes(handler)
    return Starlette(routes=routes)


def build_all():
    """Every business's agent, each at /<business>, so switching the demo's
    business needs no restart."""
    root = os.environ.get("VERTICALS", "/verticals")
    public = os.environ.get("PUBLIC_URL", "http://acme-agent:8000")
    mounts = []
    for name in sorted(os.listdir(root)):
        found = load(os.path.join(root, name))
        if found:
            mounts.append(Mount("/" + name, app=build_app(*found, url="%s/%s" % (public, name))))
    return Starlette(routes=mounts)


if __name__ == "__main__":
    uvicorn.run(build_all(), host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
