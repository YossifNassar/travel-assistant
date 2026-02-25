"""Tests for FastAPI endpoints and middleware (rate limiting, body size)."""

from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------
class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_health_exempt_from_rate_limit(self, client):
        """Health endpoint should never be rate-limited."""
        for _ in range(30):
            resp = client.get("/health")
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------
class TestChatEndpoint:
    @patch("app.main.chat", new_callable=AsyncMock)
    def test_chat_success(self, mock_chat, client):
        mock_chat.return_value = "Try visiting Barcelona!"
        resp = client.post("/chat", json={"message": "Suggest a destination"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Try visiting Barcelona!"
        assert "thread_id" in data

    @patch("app.main.chat", new_callable=AsyncMock)
    def test_chat_with_thread_id(self, mock_chat, client):
        mock_chat.return_value = "Great choice!"
        resp = client.post(
            "/chat", json={"message": "Tell me more", "thread_id": "my-thread"}
        )
        assert resp.status_code == 200
        assert resp.json()["thread_id"] == "my-thread"

    def test_chat_empty_message_rejected(self, client):
        resp = client.post("/chat", json={"message": ""})
        assert resp.status_code == 422  # Pydantic validation error

    def test_chat_missing_message_rejected(self, client):
        resp = client.post("/chat", json={})
        assert resp.status_code == 422

    @patch("app.main.chat", new_callable=AsyncMock)
    def test_chat_agent_error_returns_500(self, mock_chat, client):
        mock_chat.side_effect = RuntimeError("LLM exploded")
        resp = client.post("/chat", json={"message": "Hello"})
        assert resp.status_code == 500
        assert "something went wrong" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Streaming endpoint
# ---------------------------------------------------------------------------
class TestChatStreamEndpoint:
    @patch("app.main.chat_stream")
    def test_stream_returns_sse(self, mock_stream, client):
        async def fake_stream(message, thread_id):
            yield 'event: token\ndata: "Hello"\n\n'
            yield 'event: done\ndata: {"thread_id": "t1"}\n\n'

        mock_stream.return_value = fake_stream("hi", "t1")
        resp = client.post("/chat/stream", json={"message": "Hello"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = resp.text
        assert "event: token" in body
        assert "event: done" in body

    def test_stream_empty_message_rejected(self, client):
        resp = client.post("/chat/stream", json={"message": ""})
        assert resp.status_code == 422

    def test_stream_missing_message_rejected(self, client):
        resp = client.post("/chat/stream", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Rate limiting (slowapi)
# ---------------------------------------------------------------------------
class TestRateLimiting:
    @patch("app.main.chat", new_callable=AsyncMock)
    def test_rate_limit_triggers_after_threshold(self, mock_chat, client):
        mock_chat.return_value = "OK"

        # Send 20 requests (the limit)
        for i in range(20):
            resp = client.post("/chat", json={"message": f"msg {i}"})
            assert resp.status_code == 200, f"Request {i} should succeed"

        # 21st request should be rate-limited
        resp = client.post("/chat", json={"message": "one too many"})
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# Request body size guard
# ---------------------------------------------------------------------------
class TestBodySizeMiddleware:
    def test_oversized_body_rejected(self, client):
        huge_message = "x" * 15_000
        resp = client.post("/chat", json={"message": huge_message})
        assert resp.status_code == 413

    @patch("app.main.chat", new_callable=AsyncMock)
    def test_normal_body_accepted(self, mock_chat, client):
        mock_chat.return_value = "OK"
        resp = client.post("/chat", json={"message": "Short message"})
        assert resp.status_code == 200
