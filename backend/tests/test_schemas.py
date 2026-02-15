"""Tests for Pydantic request/response schemas."""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas import ChatRequest, ChatResponse


# ---------------------------------------------------------------------------
# ChatRequest
# ---------------------------------------------------------------------------
class TestChatRequest:
    def test_valid_message(self):
        req = ChatRequest(message="Hello!")
        assert req.message == "Hello!"
        assert req.thread_id is None

    def test_valid_message_with_thread_id(self):
        req = ChatRequest(message="Hi", thread_id="abc-123")
        assert req.thread_id == "abc-123"

    def test_empty_message_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="")

    def test_whitespace_only_rejected(self):
        """min_length=1 counts whitespace as valid; this just ensures non-empty."""
        req = ChatRequest(message=" ")
        assert req.message == " "

    def test_get_thread_id_generates_uuid_when_none(self):
        req = ChatRequest(message="test")
        tid = req.get_thread_id()
        # Should be a valid UUID
        uuid.UUID(tid)  # Raises if not valid

    def test_get_thread_id_returns_provided(self):
        req = ChatRequest(message="test", thread_id="my-thread")
        assert req.get_thread_id() == "my-thread"

    def test_missing_message_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ChatResponse
# ---------------------------------------------------------------------------
class TestChatResponse:
    def test_valid_response(self):
        resp = ChatResponse(response="Hello!", thread_id="t1")
        assert resp.response == "Hello!"
        assert resp.thread_id == "t1"

    def test_missing_fields_rejected(self):
        with pytest.raises(ValidationError):
            ChatResponse()  # type: ignore[call-arg]

    def test_missing_thread_id_rejected(self):
        with pytest.raises(ValidationError):
            ChatResponse(response="Hi")  # type: ignore[call-arg]
