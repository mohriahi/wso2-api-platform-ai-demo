"""Acme Mobile's roaming agent: an A2A 1.0 agent the A2A showcases put behind
the gateway. Given a destination, it answers with the roaming zone and what it
costs, from the same catalogue as ai-chatbot/plans.md. No model behind it, so
every answer is the same on stage.

Built on the official A2A Python SDK, which serves the Agent Card and both
A2A bindings (JSON-RPC at /, HTTP+JSON under /) from one handler.
"""
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

ZONES = {
    "A": ["Spain", "France", "Italy", "Germany", "Portugal", "Greece", "Ireland",
          "Netherlands", "Belgium", "Austria", "Switzerland", "Norway", "Sweden",
          "Denmark", "Poland", "Croatia", "Malta", "Cyprus"],
    "B": ["United States", "USA", "US", "America", "Canada", "Australia", "Japan",
          "Singapore", "Thailand", "India", "China", "Hong Kong", "South Korea",
          "Malaysia", "New Zealand", "Turkey"],
}
COSTS = {
    "A": "Roaming comes out of your plan's Zone A allowance, then £2 per GB.",
    "B": "It is not included on any plan: a Roaming Pass Zone B costs £6 a day, for 2 GB a day.",
    "C": "It is pay as you go: £6 per GB, and £1.50 a minute for calls.",
}


def answer(text):
    """The zone and price for the first destination named in the text."""
    for zone, places in ZONES.items():
        for place in places:
            if re.search(r"\b%s\b" % re.escape(place), text, re.IGNORECASE):
                return "%s is in Zone %s. %s" % (place, zone, COSTS[zone])
    if re.search(r"\b(to|in|visit|visiting)\s+[A-Z]", text):
        return "That destination is in Zone C. %s" % COSTS["C"]
    return "Tell me where you are going, for example: \"I'm going to Spain in May\"."


class RoamingExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue):
        reply = answer(get_message_text(context.message) if context.message else "")
        await event_queue.enqueue_event(new_text_message(reply, context_id=context.context_id))

    async def cancel(self, context: RequestContext, event_queue):
        return None


def build_app():
    url = os.environ.get("PUBLIC_URL", "http://acme-roaming:8000")
    card = AgentCard(
        name="Acme Roaming Agent",
        description="Tells a customer which roaming zone a destination is in, and what using their phone there costs.",
        version="1.0.0",
        supported_interfaces=[
            AgentInterface(url=url, protocol_binding="JSONRPC", protocol_version="1.0"),
            AgentInterface(url=url, protocol_binding="HTTP+JSON", protocol_version="1.0"),
        ],
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[AgentSkill(id="roaming-zone", name="Roaming zone and price",
                           description="The zone a destination is in, and the price of using a phone there.",
                           tags=["roaming", "travel"], examples=["I'm going to Spain in May"])],
    )
    handler = DefaultRequestHandler(agent_executor=RoamingExecutor(), task_store=InMemoryTaskStore(), agent_card=card)
    routes = create_agent_card_routes(card) + create_jsonrpc_routes(handler, "/") + create_rest_routes(handler)
    return Starlette(routes=routes)


if __name__ == "__main__":
    uvicorn.run(build_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
