import httpx
import json
from datetime import datetime

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL          = "google/gemini-3.1-flash-lite"

SYSTEM_PROMPT = """You are a smart personal assistant that understands natural language messages about meetings, tasks, and schedules.

Your job is to analyze a user's message and return a JSON response ONLY — no explanation, no markdown, just raw JSON.

Today's date and time will be provided in the user message.

Possible actions you must return:
1. "save"       — user wants to add a meeting or task
2. "show_today" — user wants to see today's schedule
3. "show_all"   — user wants to see all upcoming items
4. "delete"     — user wants to remove something
5. "chat"       — general conversation, not a schedule action

For action "save", return:
{
  "action": "save",
  "item": {
    "title": "short clear title",
    "type": "meeting" or "task",
    "date": "YYYY-MM-DD",
    "time": "HH:MM" (24-hour format, null if no time given),
    "note": "any extra detail or null"
  },
  "reply": "friendly confirmation message like a real assistant would say"
}

For action "show_today":
{ "action": "show_today" }

For action "show_all":
{ "action": "show_all" }

For action "delete":
{
  "action": "delete",
  "title_hint": "keyword from the item title to delete"
}

For action "chat":
{
  "action": "chat",
  "reply": "friendly natural response"
}

Rules:
- Understand relative dates: "today", "tomorrow", "Friday", "next week Monday" etc. — resolve them to YYYY-MM-DD using the provided current date
- Understand times like "3pm", "11:30", "half past 2", "morning" (use 09:00), "evening" (use 18:00), "night" (use 20:00)
- If no date is given but a time is, assume today
- Be friendly and natural in reply messages — like a real personal assistant
- Return ONLY valid JSON, nothing else"""


class AIHandler:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client  = httpx.AsyncClient(timeout=30)

    async def process_message(self, user_text: str, now_ist: datetime) -> dict:
        date_context = now_ist.strftime("%A, %d %B %Y, %I:%M %p IST")

        user_content = f"Current date/time: {date_context}\n\nUser message: {user_text}"

        try:
            response = await self.client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://personal-assistant-bot",
                    "X-Title": "Personal Assistant Bot"
                },
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": user_content}
                    ],
                    "max_tokens": 500,
                    "temperature": 0.2
                }
            )

            data    = response.json()
            raw     = data["choices"][0]["message"]["content"].strip()

            # Strip markdown code fences if model added them
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            result = json.loads(raw)
            return result

        except Exception as e:
            return {
                "action": "chat",
                "reply": f"Sorry, I had trouble understanding that. Could you rephrase? (Error: {str(e)[:80]})"
            }
