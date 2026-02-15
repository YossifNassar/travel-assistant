"""FastAPI application for the Travel Assistant backend."""

import logging

from dotenv import load_dotenv

load_dotenv()  # Load .env before anything else uses env vars

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.schemas import ChatRequest, ChatResponse
from app.agent import chat

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter (slowapi — in-memory, per-IP)
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["20/minute"])

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Travel Assistant API",
    description="AI-powered travel planning assistant using LangGraph + Groq",
    version="1.0.0",
)

# Register the rate limiter with the app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# CORS — allow the Next.js frontend
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request-size guard
# ---------------------------------------------------------------------------
MAX_BODY_SIZE = 10_000  # 10 KB max request body


@app.middleware("http")
async def body_size_middleware(request: Request, call_next):
    """Reject excessively large request bodies."""
    if request.method in ("POST", "PUT", "PATCH"):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large."},
            )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
@limiter.exempt
async def health():
    """Health check endpoint (exempt from rate limiting)."""
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat_endpoint(request: Request, chat_request: ChatRequest):
    """Process a user message and return the assistant's response.

    Maintains conversation context via thread_id.
    """
    thread_id = chat_request.get_thread_id()

    logger.info(f"[thread={thread_id}] User: {chat_request.message[:80]}...")

    try:
        response = await chat(chat_request.message, thread_id)
    except Exception as e:
        logger.error(f"[thread={thread_id}] Agent error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Sorry, something went wrong processing your request. Please try again.",
        )

    logger.info(f"[thread={thread_id}] Assistant: {response[:80]}...")

    return ChatResponse(response=response, thread_id=thread_id)
    