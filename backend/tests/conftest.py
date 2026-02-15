"""Shared fixtures for backend tests."""

import os

import pytest
from fastapi.testclient import TestClient

# Ensure dummy env vars are set before importing app modules
os.environ.setdefault("GROQ_API_KEY", "test-key-not-real")
os.environ.setdefault("OPENWEATHER_API_KEY", "test-key-not-real")

from app.main import app, limiter  # noqa: E402


@pytest.fixture()
def client():
    """Synchronous test client for the FastAPI app."""
    # Reset rate limiter storage between tests
    limiter.reset()
    return TestClient(app)
