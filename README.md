# Travel Assistant

AI-powered travel planning assistant built with **Next.js**, **FastAPI**, **LangGraph**, and **Groq**.

Handles destination recommendations, packing suggestions (with chain-of-thought reasoning), and local attractions — augmented with real-time weather, country data, currency exchange rates, and public holidays from external APIs. All external APIs are free and require no API keys (except Groq for the LLM).

## Architecture

```
┌──────────────────┐     POST /chat     ┌──────────────────────────────────┐
│   Next.js Chat   │ ──────────────────▶│        FastAPI Backend          │
│   (port 3000)    │ ◀──────────────────│        (port 8001)             │
└──────────────────┘                    │                                │
                                        │  ┌───────────────────────┐     │
                                        │  │  LangGraph ReAct Agent │     │
                                        │  │  + MemorySaver         │     │
                                        │  └───────┬───────────────┘     │
                                        │          │                     │
                                        │    ┌─────┴─────┐              │
                                        │    ▼           ▼              │
                                        │  Tools        Groq LLM       │
                                        │  ├─ Weather    (Llama 4     │
                                        │  ├─ Country     Scout)      │
                                        │  ├─ Exchange               │
                                        │  └─ Holidays               │
                                        └──────────────────────────────┘
                                             │    │    │    │
                                             ▼    ▼    ▼    ▼
                                        Open- Rest  Frank- Nager
                                        Meteo Count furter .Date
```

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** (Python package manager)
- **Node.js 18+** and npm
- **Groq API key** (free): https://console.groq.com

## Quick Start

### 1. Clone and set up environment variables

```bash
cd backend
cp .env.example .env
# Edit .env and add your Groq API key:
#   GROQ_API_KEY=your_key_here
# (All other APIs are free and require no keys)
```

### 2. Start the backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8001
```

The API will be available at http://localhost:8001. Test with:

```bash
curl http://localhost:8001/health
```

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 in your browser.

## API Endpoints

| Method | Path      | Description                    |
|--------|-----------|--------------------------------|
| GET    | `/health` | Health check                   |
| POST   | `/chat`   | Send a message, get a response |

### POST /chat

**Request:**
```json
{
  "message": "Recommend a beach destination for March",
  "thread_id": "optional-session-id"
}
```

**Response:**
```json
{
  "response": "Here are 3 great beach destinations for March...",
  "thread_id": "abc123"
}
```

The `thread_id` maintains conversation context. Omit it on the first message to have one auto-generated; include it on subsequent messages for follow-up questions.

## Running Tests

```bash
cd backend
uv sync --extra dev
uv run pytest tests/ -v
```

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI app with CORS and endpoints
│   │   ├── agent.py       # LangGraph ReAct agent setup
│   │   ├── tools.py       # Weather, country, exchange rate, holiday tools
│   │   ├── prompts.py     # System prompt engineering
│   │   └── schemas.py     # Request/response models
│   ├── pyproject.toml
│   └── .env.example
├── frontend/
│   └── src/app/
│       ├── page.tsx        # Chat interface
│       ├── layout.tsx      # App layout
│       └── globals.css     # Styles
├── transcripts/            # Sample conversation demos
├── PROMPT_ENGINEERING.md   # Prompt engineering decisions
└── README.md
```

## Key Features

- **3 Travel Query Types:** Destination recommendations, packing lists, local attractions
- **Chain-of-Thought Reasoning:** Packing suggestions use step-by-step reasoning with weather data
- **External Data Augmentation:** Weather forecasts (Open-Meteo), country info (RestCountries), exchange rates (Frankfurter), and public holidays (Nager.Date) — all free, no API keys
- **Smart Tool Routing:** Agent decides when to call APIs vs. use LLM knowledge based on query type
- **Conversation Memory:** Context persists across messages via LangGraph checkpointer
- **Error Handling:** Graceful fallbacks when tools fail, honest uncertainty acknowledgment
- **Modern Chat UI:** Clean interface with typing indicators, suggestions, and auto-scroll

## Sample Conversations

See the `transcripts/` directory for annotated example conversations demonstrating:

1. **Destination recommendation** with follow-up questions and context retention
2. **Packing suggestions** with chain-of-thought reasoning and weather tool usage
3. **Local attractions** with country info API integration

## Technology Choices

| Component       | Technology                   | Why                                              |
|-----------------|------------------------------|--------------------------------------------------|
| LLM             | Groq (Llama 4 Scout)         | Free tier (no credit card), fast inference, strong tool calling |
| Agent Framework | LangGraph (ReAct)            | Modern agent pattern with built-in memory         |
| Backend         | FastAPI                      | Async-native, auto-docs, Pydantic integration     |
| Frontend        | Next.js + Tailwind           | Fast development, modern React, utility CSS       |
| Weather API     | Open-Meteo + Nominatim       | Free, no key, 7-day forecasts, geocoding          |
| Country API     | RestCountries                | Free, no key needed, comprehensive data           |
| Exchange Rates  | Frankfurter (ECB data)       | Free, no key, real-time currency conversion       |
| Holidays API    | Nager.Date                   | Free, no key, public holidays by country          |

> **Note:** Groq provides a free-tier API with no credit card required, satisfying the assignment's requirement for a free LLM API. All four external data APIs (Open-Meteo, RestCountries, Frankfurter, Nager.Date) are completely free and require no API keys or registration.
