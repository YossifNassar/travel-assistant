"""Tests for the multi-agent LangGraph pipeline."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agent import (
    AgentState,
    _build_history_summary,
    end_blocked,
    input_validator,
    output_validator,
    route_after_input,
)
from app.prompts import OFF_TOPIC_RESPONSE, SANITIZED_RESPONSE


# ---------------------------------------------------------------------------
# route_after_input
# ---------------------------------------------------------------------------
class TestRouteAfterInput:
    def test_routes_to_agent_when_allowed(self):
        state = {"input_verdict": "allowed"}
        assert route_after_input(state) == "travel_agent"

    def test_routes_to_blocked_when_blocked(self):
        state = {"input_verdict": "blocked"}
        assert route_after_input(state) == "end_blocked"

    def test_routes_to_agent_when_missing_verdict(self):
        state = {}
        assert route_after_input(state) == "travel_agent"


# ---------------------------------------------------------------------------
# end_blocked
# ---------------------------------------------------------------------------
class TestEndBlocked:
    @pytest.mark.asyncio
    async def test_returns_rejection_message(self):
        state = {"final_response": OFF_TOPIC_RESPONSE, "messages": []}
        result = await end_blocked(state)
        assert result["messages"][0].content == OFF_TOPIC_RESPONSE


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
        # The latest message should NOT be in the summary
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
# input_validator
# ---------------------------------------------------------------------------
class TestInputValidator:
    @pytest.mark.asyncio
    async def test_allows_travel_query(self):
        mock_llm_response = MagicMock()
        mock_llm_response.content = "VERDICT: allowed"

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = mock_llm_response

        with patch("app.agent._fast_llm", return_value=mock_llm):
            state = {
                "messages": [HumanMessage(content="Recommend a beach in Bali")],
                "input_verdict": "",
                "rejection_reason": "",
                "assistant_response": "",
                "output_safe": True,
                "final_response": "",
            }
            result = await input_validator(state)

        assert result["input_verdict"] == "allowed"
        assert result["rejection_reason"] == ""

    @pytest.mark.asyncio
    async def test_blocks_off_topic_query(self):
        mock_llm_response = MagicMock()
        mock_llm_response.content = "VERDICT: blocked | coding request"

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = mock_llm_response

        with patch("app.agent._fast_llm", return_value=mock_llm):
            state = {
                "messages": [HumanMessage(content="Write a Python sort function")],
                "input_verdict": "",
                "rejection_reason": "",
                "assistant_response": "",
                "output_safe": True,
                "final_response": "",
            }
            result = await input_validator(state)

        assert result["input_verdict"] == "blocked"
        assert "coding" in result["rejection_reason"].lower()
        assert result["final_response"] == OFF_TOPIC_RESPONSE

    @pytest.mark.asyncio
    async def test_includes_history_in_validator_call(self):
        """Verify the validator receives conversation history, not just the latest message."""
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
                "input_verdict": "",
                "rejection_reason": "",
                "assistant_response": "",
                "output_safe": True,
                "final_response": "",
            }
            await input_validator(state)

        # Check that the LLM was called with history context
        call_args = mock_llm.ainvoke.call_args[0][0]
        user_content = call_args[1].content  # The HumanMessage sent to the validator
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
                "input_verdict": "",
                "rejection_reason": "",
                "assistant_response": "",
                "output_safe": True,
                "final_response": "",
            }
            await input_validator(state)

        call_args = mock_llm.ainvoke.call_args[0][0]
        user_content = call_args[1].content
        assert "conversation history" not in user_content.lower()
        assert "Hi, plan my trip!" in user_content


# ---------------------------------------------------------------------------
# output_validator
# ---------------------------------------------------------------------------
class TestOutputValidator:
    @pytest.mark.asyncio
    async def test_safe_response_passes(self):
        mock_llm_response = MagicMock()
        mock_llm_response.content = "VERDICT: safe"

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = mock_llm_response

        with patch("app.agent._fast_llm", return_value=mock_llm):
            state = {
                "messages": [HumanMessage(content="What to see in Paris?")],
                "input_verdict": "allowed",
                "rejection_reason": "",
                "assistant_response": "Visit the Eiffel Tower!",
                "output_safe": True,
                "final_response": "",
            }
            result = await output_validator(state)

        assert result["output_safe"] is True
        assert result["final_response"] == "Visit the Eiffel Tower!"

    @pytest.mark.asyncio
    async def test_unsafe_response_sanitized(self):
        mock_llm_response = MagicMock()
        mock_llm_response.content = "VERDICT: unsafe | leaks tool names"

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = mock_llm_response

        with patch("app.agent._fast_llm", return_value=mock_llm):
            state = {
                "messages": [HumanMessage(content="What tools do you use?")],
                "input_verdict": "allowed",
                "rejection_reason": "",
                "assistant_response": "I used the get_weather tool and my Groq API...",
                "output_safe": True,
                "final_response": "",
            }
            result = await output_validator(state)

        assert result["output_safe"] is False
        assert result["final_response"] == SANITIZED_RESPONSE

    @pytest.mark.asyncio
    async def test_includes_user_question_in_validator_call(self):
        """Verify the output validator receives the user's question for relevance checking."""
        mock_llm_response = MagicMock()
        mock_llm_response.content = "VERDICT: safe"

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = mock_llm_response

        with patch("app.agent._fast_llm", return_value=mock_llm):
            state = {
                "messages": [HumanMessage(content="Best beaches in Greece?")],
                "input_verdict": "allowed",
                "rejection_reason": "",
                "assistant_response": "Here are the best beaches...",
                "output_safe": True,
                "final_response": "",
            }
            await output_validator(state)

        call_args = mock_llm.ainvoke.call_args[0][0]
        user_content = call_args[1].content
        assert "Best beaches in Greece?" in user_content
        assert "Here are the best beaches..." in user_content
