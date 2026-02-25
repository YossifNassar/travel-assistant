"""Tests for the travel assistant agent and middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from app.agent import (
    _build_history_summary,
    input_guardrail,
)
from app.prompts import OFF_TOPIC_RESPONSE


# ---------------------------------------------------------------------------
# _build_history_summary
# ---------------------------------------------------------------------------
class TestBuildHistorySummary:
    def test_no_history_for_single_message(self):
        messages = [HumanMessage(content="Hello")]
        assert _build_history_summary(messages) == ""

    def test_no_history_for_empty_messages(self):
        assert _build_history_summary([]) == ""

    def test_includes_prior_messages(self):
        messages = [
            HumanMessage(content="Recommend a beach in Bali"),
            AIMessage(content="Bali has beautiful beaches!"),
            HumanMessage(content="Tell me more"),
        ]
        summary = _build_history_summary(messages)
        assert "User: Recommend a beach in Bali" in summary
        assert "Assistant: Bali has beautiful beaches!" in summary
        assert "Tell me more" not in summary

    def test_truncates_long_messages(self):
        long_text = "x" * 300
        messages = [
            HumanMessage(content=long_text),
            HumanMessage(content="follow-up"),
        ]
        summary = _build_history_summary(messages)
        assert "..." in summary
        assert len(summary) < 300


# ---------------------------------------------------------------------------
# input_guardrail (@before_agent middleware)
# ---------------------------------------------------------------------------
class TestInputGuardrail:
    @pytest.mark.asyncio
    async def test_allows_travel_query(self):
        mock_llm_response = MagicMock()
        mock_llm_response.content = "VERDICT: allowed"

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = mock_llm_response

        with patch("app.agent._fast_llm", return_value=mock_llm):
            state = {
                "messages": [HumanMessage(content="Recommend a beach in Bali")],
            }
            result = await input_guardrail.abefore_agent(state, Runtime())

        assert result is None

    @pytest.mark.asyncio
    async def test_blocks_off_topic_query(self):
        mock_llm_response = MagicMock()
        mock_llm_response.content = "VERDICT: blocked | coding request"

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = mock_llm_response

        with patch("app.agent._fast_llm", return_value=mock_llm):
            state = {
                "messages": [HumanMessage(content="Write a Python sort function")],
            }
            result = await input_guardrail.abefore_agent(state, Runtime())

        assert result is not None
        assert result["jump_to"] == "end"
        ai_msg = result["messages"][0]
        assert ai_msg.content == OFF_TOPIC_RESPONSE

    @pytest.mark.asyncio
    async def test_includes_history_in_validator_call(self):
        """Verify the guardrail receives conversation history, not just the latest message."""
        mock_llm_response = MagicMock()
        mock_llm_response.content = "VERDICT: allowed"

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = mock_llm_response

        with patch("app.agent._fast_llm", return_value=mock_llm):
            state = {
                "messages": [
                    HumanMessage(content="I want to visit Tokyo"),
                    AIMessage(content="Tokyo is amazing! Here are some tips..."),
                    HumanMessage(content="What about food there?"),
                ],
            }
            await input_guardrail.abefore_agent(state, Runtime())

        call_args = mock_llm.ainvoke.call_args[0][0]
        user_content = call_args[1].content
        assert "conversation history" in user_content.lower()
        assert "Tokyo" in user_content
        assert "What about food there?" in user_content

    @pytest.mark.asyncio
    async def test_no_history_block_for_first_message(self):
        """First message should not include a history section."""
        mock_llm_response = MagicMock()
        mock_llm_response.content = "VERDICT: allowed"

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = mock_llm_response

        with patch("app.agent._fast_llm", return_value=mock_llm):
            state = {
                "messages": [HumanMessage(content="Hi, plan my trip!")],
            }
            await input_guardrail.abefore_agent(state, Runtime())

        call_args = mock_llm.ainvoke.call_args[0][0]
        user_content = call_args[1].content
        assert "conversation history" not in user_content.lower()
        assert "Hi, plan my trip!" in user_content
