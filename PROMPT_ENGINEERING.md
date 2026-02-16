# Prompt Engineering Decisions

This document explains the key prompt engineering decisions behind the Travel Assistant.

## 1. Chain-of-Thought for Packing Suggestions

**Decision:** When users ask what to pack, the system prompt instructs the LLM to follow a 4-step reasoning process before answering.

**Why:** Packing is inherently multi-factor — it depends on weather, trip type, activities, and duration. Without guided reasoning, LLMs tend to produce generic lists. The chain-of-thought approach forces the model to:

1. Check real weather data first (grounding the response in facts)
2. Consider the trip context (duration, purpose)
3. Think through activity-specific needs
4. Then organize items by category

**Result:** Packing suggestions are noticeably more personalized and complete. The visible reasoning also builds user trust — they can see *why* each item is recommended rather than getting an opaque list.

## 2. Data Augmentation Routing (Tool Use Decision Method)

**Decision:** The system prompt contains explicit rules for when to use external APIs versus LLM knowledge.

**Five categories:**
- **Weather tool (Open-Meteo):** Used for current conditions + 7-day forecast, packing, weather-dependent planning
- **Country info tool (RestCountries):** Used for factual queries (currency, language, timezone)
- **Exchange rate tool (Frankfurter):** Used for currency conversion and budget advice
- **Public holidays tool (Nager.Date):** Used for flagging holidays, festivals, or potential closures
- **LLM knowledge:** Used for subjective recommendations, cultural tips, itineraries

**Why:** Without clear routing rules, the LLM either over-relies on tools (calling weather API for every message) or under-uses them (answering currency questions from memory, risking outdated info). Explicit rules in the prompt give the model a clear decision framework. All four external APIs are free and require no API keys, making the system easy to set up.

**Alternative considered:** A separate classifier/router node in the LangGraph that determines tool use before the main agent. Rejected because the ReAct pattern with good tool descriptions handles this well — adding a router would increase latency without meaningful improvement for this use case.

## 3. Error Handling Strategy

**Decision:** The prompt instructs the LLM to handle three failure modes:

1. **Tool failures** → Fall back to general knowledge, inform the user
2. **Vague queries** → Ask one focused clarifying question
3. **Uncertain facts** → Acknowledge uncertainty, recommend official sources

**Why:** LLMs naturally try to be helpful even when they shouldn't. Without explicit instructions to acknowledge limitations, the model fabricates specific prices, hours, or visa requirements. The "never fabricate specific details" rule trades some helpfulness for trustworthiness — a better tradeoff for travel planning where wrong info can have real consequences.

## 4. Context Management Approach

**Decision:** Using LangGraph's `MemorySaver` checkpointer with thread-based memory, plus prompt instructions for conversational coherence.

**How it works:**
- LangGraph's checkpointer stores the full message history per `thread_id`
- The system prompt instructs the model to reference previous context naturally
- Follow-up questions build on earlier information without repeating

**Why not summarization memory?** For a demo/assignment context, the conversation buffer is sufficient. Real production usage with very long conversations would benefit from `ConversationSummaryMemory` to stay within context windows, but for typical travel planning conversations (10–20 turns), the full history fits easily.

## 5. Response Style Guidelines

**Decision:** The prompt specifies bullet points, 3–5 recommendations per list, and practical details inline.

**Why:** Travel planning answers tend to be long. Without format constraints, the LLM produces walls of text. Bullet points make responses scannable on mobile. The 3–5 item limit prevents overwhelming the user while still offering meaningful choice. Inline practical details (prices, times, distances) save the user from asking follow-up questions.

## 6. Personality and Tone

**Decision:** "Warm and conversational" with enthusiasm that's not over-the-top.

**Why:** Travel planning is exciting for users — the assistant should match that energy without feeling artificial. The prompt avoids emoji and excessive exclamation marks, opting for a knowledgeable-friend tone rather than a hyper-enthusiastic chatbot tone. This builds credibility for the practical advice portions.
