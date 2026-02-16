"""Multi-agent LangGraph for the Travel Assistant.

Architecture:
  User message → Input Validator → Travel Agent → Output Validator → Response

The input validator gates off-topic / injection / internals-probing messages.
The output validator catches any response that leaks internals or non-travel content.
Both validators use a fast, cheap LLM (Llama 3.1 8B).
The travel agent uses the larger model with tools.
"""

import os
from functools import lru_cache
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent

from app.prompts import (
    INPUT_VALIDATOR_PROMPT,
    OFF_TOPIC_RESPONSE,
    OUTPUT_VALIDATOR_PROMPT,
    SANITIZED_RESPONSE,
    TRAVEL_ASSISTANT_SYSTEM_PROMPT,
)
from app.tools import get_country_info, get_exchange_rate, get_public_holidays, get_weather


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]  # conversation history
    input_verdict: str  # "allowed" | "blocked"
    rejection_reason: str  # why input was blocked
    assistant_response: str  # raw response from travel agent
    output_safe: bool  # whether output passed validation
    final_response: str  # the response to return to the user


# ---------------------------------------------------------------------------
# LLMs (lazy-initialized)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _fast_llm() -> ChatGroq:
    """Cheap/fast model for validators."""
    return ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0,
        api_key=os.environ["GROQ_API_KEY"],
    )


@lru_cache(maxsize=1)
def _main_llm() -> ChatGroq:
    """Main model for the travel agent."""
    return ChatGroq(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        temperature=0.4,
        api_key=os.environ["GROQ_API_KEY"],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
MAX_HISTORY_TURNS = 6  # max recent messages to include for validator context


def _build_history_summary(messages: list) -> str:
    """Build a concise conversation-history block for validator context.

    Returns an empty string when there is no prior history (first message).
    """
    # All messages except the very last one (which is the new user input)
    prior = messages[:-1] if len(messages) > 1 else []
    if not prior:
        return ""

    # Keep only the most recent turns to stay within token budget
    recent = prior[-MAX_HISTORY_TURNS:]
    lines: list[str] = []
    for msg in recent:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        text = msg.content if hasattr(msg, "content") else str(msg)
        # Truncate long messages to keep the context compact
        if len(text) > 200:
            text = text[:200] + "..."
        lines.append(f"{role}: {text}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Node 1: Input Validator
# ---------------------------------------------------------------------------
async def input_validator(state: AgentState) -> dict:
    """Classify the user's latest message as allowed or blocked.

    Sends the recent conversation history alongside the new message so the
    validator can judge ambiguous follow-ups in context.
    """
    last_message = state["messages"][-1]
    user_text = last_message.content if hasattr(last_message, "content") else str(last_message)

    history_block = _build_history_summary(state["messages"])

    # Build the content the validator will see
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
        reason = ""
        if "|" in verdict_text:
            reason = verdict_text.split("|", 1)[1].strip()
        return {
            "input_verdict": "blocked",
            "rejection_reason": reason,
            "final_response": OFF_TOPIC_RESPONSE,
        }

    return {"input_verdict": "allowed", "rejection_reason": ""}


# ---------------------------------------------------------------------------
# Node 2: Travel Agent (wraps the prebuilt ReAct agent)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _get_react_agent():
    """Build and cache the inner ReAct agent (no checkpointer — outer graph handles memory)."""
    return create_react_agent(
        model=_main_llm(),
        tools=[get_weather, get_country_info, get_exchange_rate, get_public_holidays],
        prompt=TRAVEL_ASSISTANT_SYSTEM_PROMPT,
    )


async def travel_agent(state: AgentState) -> dict:
    """Run the travel ReAct agent on the conversation messages.

    Handles Groq tool_use_failed errors by extracting the partial response
    or falling back to a direct LLM call without tools.
    """
    import json
    import logging

    logger = logging.getLogger(__name__)
    react_agent = _get_react_agent()

    try:
        result = await react_agent.ainvoke({"messages": state["messages"]})
        ai_message = result["messages"][-1]
        return {"assistant_response": ai_message.content}

    except Exception as e:
        error_str = str(e)

        # Groq tool_use_failed: model generated text that was misread as a tool call.
        # Try to salvage the partial response from the error payload.
        if "tool_use_failed" in error_str and "failed_generation" in error_str:
            logger.warning("Groq tool_use_failed — retrying without tools")

            # Attempt: call the LLM directly without tools bound
            try:
                llm = _main_llm()
                direct_result = await llm.ainvoke(
                    [SystemMessage(content=TRAVEL_ASSISTANT_SYSTEM_PROMPT)]
                    + state["messages"]
                )
                return {"assistant_response": direct_result.content}
            except Exception as retry_err:
                logger.error(f"Retry without tools also failed: {retry_err}")

        # If all else fails, return a friendly fallback
        return {
            "assistant_response": (
                "I ran into a temporary issue generating my response. "
                "Could you try rephrasing your question? I'm here to help with your travel plans!"
            )
        }


# ---------------------------------------------------------------------------
# Node 3: Output Validator
# ---------------------------------------------------------------------------
async def output_validator(state: AgentState) -> dict:
    """Check the travel agent's response for safety and relevance.

    Passes the user's question alongside the response so the validator can
    judge whether the answer is actually relevant to what was asked.
    """
    response = state["assistant_response"]

    # Extract the latest user message for context
    user_text = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            user_text = msg.content if hasattr(msg, "content") else str(msg)
            break

    validator_input = (
        f"## User's question\n{user_text}\n\n"
        f"## Assistant's response to review\n{response}"
    )

    llm = _fast_llm()
    result = await llm.ainvoke([
        SystemMessage(content=OUTPUT_VALIDATOR_PROMPT),
        HumanMessage(content=validator_input),
    ])

    verdict_text = result.content.strip()

    if "unsafe" in verdict_text.lower():
        return {
            "output_safe": False,
            "final_response": SANITIZED_RESPONSE,
            # Still add the sanitized response to messages for context
            "messages": [AIMessage(content=SANITIZED_RESPONSE)],
        }

    return {
        "output_safe": True,
        "final_response": response,
        "messages": [AIMessage(content=response)],
    }


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------
def route_after_input(state: AgentState) -> Literal["travel_agent", "end_blocked"]:
    """Route based on input validator verdict."""
    if state.get("input_verdict") == "blocked":
        return "end_blocked"
    return "travel_agent"


# ---------------------------------------------------------------------------
# Blocked end node — adds the rejection message to conversation history
# ---------------------------------------------------------------------------
async def end_blocked(state: AgentState) -> dict:
    """Terminal node for blocked input — adds rejection to messages."""
    return {
        "messages": [AIMessage(content=OFF_TOPIC_RESPONSE)],
    }


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------
_checkpointer = MemorySaver()


@lru_cache(maxsize=1)
def _build_graph():
    """Construct the multi-agent StateGraph."""
    builder = StateGraph(AgentState)

    # Add nodes
    builder.add_node("input_validator", input_validator)
    builder.add_node("travel_agent", travel_agent)
    builder.add_node("output_validator", output_validator)
    builder.add_node("end_blocked", end_blocked)

    # Edges
    builder.add_edge(START, "input_validator")
    builder.add_conditional_edges(
        "input_validator",
        route_after_input,
        {"travel_agent": "travel_agent", "end_blocked": "end_blocked"},
    )
    builder.add_edge("travel_agent", "output_validator")
    builder.add_edge("output_validator", END)
    builder.add_edge("end_blocked", END)

    return builder.compile(checkpointer=_checkpointer)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def chat(message: str, thread_id: str) -> str:
    """Send a user message through the multi-agent pipeline.

    Flow: Input Validator → Travel Agent → Output Validator

    Args:
        message: The user's text message.
        thread_id: Unique conversation thread identifier for memory.

    Returns:
        The validated assistant response.
    """
    graph = _build_graph()
    config = {"configurable": {"thread_id": thread_id}}

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=message)]},
        config=config,
    )

    return result.get("final_response", OFF_TOPIC_RESPONSE)
