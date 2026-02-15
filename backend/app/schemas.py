from pydantic import BaseModel, Field
from typing import Optional
import uuid


class ChatRequest(BaseModel):
    """Request body for the /chat endpoint."""

    message: str = Field(..., min_length=1, description="The user's message")
    thread_id: Optional[str] = Field(
        default=None,
        description="Conversation thread ID. Auto-generated if not provided.",
    )

    def get_thread_id(self) -> str:
        return self.thread_id or str(uuid.uuid4())


class ChatResponse(BaseModel):
    """Response body for the /chat endpoint."""

    response: str = Field(..., description="The assistant's reply")
    thread_id: str = Field(..., description="Conversation thread ID for follow-ups")
