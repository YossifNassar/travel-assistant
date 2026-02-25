"""Travel Assistant agent with middleware-based input validation.

Architecture:
  @before_agent guardrail → create_agent (LLM + tools + checkpointer)

The input guardrail middleware validates each user message before the agent
loop begins.  Blocked messages short-circuit via jump_to="end" and return
a canned OFF_TOPIC_RESPONSE.  Allowed messages proceed to the tool-calling
agent which streams tokens via SSE for a modern chat experience.
"""

import json
import logging
import os
from functools import lru_cache
from typing import AsyncGenerator

from langchain.agents import create_agent
from langchain.agents.middleware import before_agent, AgentState
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langgraph.checkpoint.memory import MemorySaver

from app.prompts import (
    INPUT_VALIDATOR_PROMPT,
    OFF_TOPIC_RESPONSE,
    TRAVEL_ASSISTANT_SYSTEM_PROMPT,
)
from app.tools import get_country_info, get_exchange_rate, get_public_holidays, get_weather

logger = logging.getLogger(__name__)

tavily_search = TavilySearch(max_results=5, topic="general")

FALLBACK_ERROR = (
    "I ran into a temporary issue generating my response. "
    "Could you try rephrasing your question? I'm here to help with your travel plans!"
)


# ---------------------------------------------------------------------------
# LLMs (lazy-initialized)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _fast_llm() -> ChatOpenAI:
    """Cheap/fast model for the input guardrail."""
    return ChatOpenAI(
        model="gpt-5-mini",
        temperature=0,
        api_key=os.environ["OPENAI_API_KEY"],
    )


@lru_cache(maxsize=1)
def _main_llm() -> ChatOpenAI:
    """Main model for the travel agent."""
    return ChatOpenAI(
        model="gpt-5.2",
        temperature=0.4,
        api_key=os.environ["OPENAI_API_KEY"],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
MAX_HISTORY_TURNS = 6


def _build_history_summary(messages: list) -> str:
    """Build a concise conversation-history block for validator context.

    Returns an empty string when there is no prior history (first message).
    """
    prior = messages[:-1] if len(messages) > 1 else []
    if not prior:
        return ""

    recent = prior[-MAX_HISTORY_TURNS:]
    lines: list[str] = []
    for msg in recent:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        text = msg.content if hasattr(msg, "content") else str(msg)
        if len(text) > 200:
            text = text[:200] + "..."
        lines.append(f"{role}: {text}")

    return "\n".join(lines)


def _sse(event: str, data) -> str:
    """Format a server-sent event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Middleware: Input Guardrail
# ---------------------------------------------------------------------------
@before_agent(can_jump_to=["end"])
async def input_guardrail(state: AgentState, runtime) -> dict | None:
    """Validate the latest user message; block off-topic / injection attempts."""
    last_message = state["messages"][-1]
    user_text = last_message.content if hasattr(last_message, "content") else str(last_message)

    history_block = _build_history_summary(state["messages"])

    if history_block:
        validator_input = (
            f"## Recent conversation history\n{history_block}\n\n"
            f"## Latest user message to classify\n{user_text}"
        )
    else:
        validator_input = f"## Latest user message to classify\n{user_text}"

    llm = _fast_llm()
    result = await llm.ainvoke([
        SystemMessage(content=INPUT_VALIDATOR_PROMPT),
        HumanMessage(content=validator_input),
    ])

    verdict_text = result.content.strip()

    if "blocked" in verdict_text.lower():
        return {
            "messages": [AIMessage(content=OFF_TOPIC_RESPONSE)],
            "jump_to": "end",
        }

    return None


# ---------------------------------------------------------------------------
# Build the agent
# ---------------------------------------------------------------------------
_checkpointer = MemorySaver()


@lru_cache(maxsize=1)
def _build_agent():
    """Construct a single create_agent with middleware guardrail and checkpointer."""
    return create_agent(
        model=_main_llm(),
        tools=[get_weather, get_country_info, get_exchange_rate, get_public_holidays, tavily_search],
        system_prompt=TRAVEL_ASSISTANT_SYSTEM_PROMPT,
        middleware=[input_guardrail],
        checkpointer=_checkpointer,
    )


# ---------------------------------------------------------------------------
# Public API — non-streaming
# ---------------------------------------------------------------------------
async def chat(message: str, thread_id: str) -> str:
    """Send a user message through the agent (request-response)."""
    agent = _build_agent()
    config = {"configurable": {"thread_id": thread_id}}

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=message)]},
        config=config,
    )

    return result["messages"][-1].content


# ---------------------------------------------------------------------------
# Public API — streaming (SSE)
# ---------------------------------------------------------------------------
async def chat_stream(message: str, thread_id: str) -> AsyncGenerator[str, None]:
    """Stream the assistant's response as SSE events.

    Uses agent.astream_events() to propagate on_chat_model_stream tokens.
    The MemorySaver checkpointer manages conversation memory automatically.
    Events are filtered to the "model" node (the model-calling node inside
    create_agent) so that the guardrail middleware's LLM call is excluded.

    Event types:
      token — incremental text chunk (JSON string)
      done  — stream complete, payload includes thread_id
    """
    agent = _build_agent()
    config = {"configurable": {"thread_id": thread_id}}
    streamed_any = False

    async for event in agent.astream_events(
        {"messages": [HumanMessage(content=message)]},
        config=config,
        version="v2",
    ):
        if (
            event["event"] == "on_chat_model_stream"
            and event.get("metadata", {}).get("langgraph_node") == "model"
        ):
            token = getattr(event["data"]["chunk"], "content", "")
            if token:
                streamed_any = True
                yield _sse("token", token)

    if not streamed_any:
        final_state = await agent.aget_state(config)
        last_msg = final_state.values.get("messages", [])
        response = last_msg[-1].content if last_msg else OFF_TOPIC_RESPONSE
        yield _sse("token", response)

    yield _sse("done", {"thread_id": thread_id})
