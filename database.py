import httpx
from datetime import datetime, timedelta
import pytz
import os

IST = pytz.timezone("Asia/Kolkata")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://euelfvzjmvmpnohtnebl.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

BASE = f"{SUPABASE_URL}/rest/v1/items"


class Database:
    def __init__(self):
        self.client = httpx.Client(timeout=10)

    def _headers(self):
        key = os.environ.get("SUPABASE_KEY", SUPABASE_KEY)
        return {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    # ── Save a new item ───────────────────────────────────
    def save_item(self, item: dict):
        payload = {
            "title":            item.get("title", "Untitled"),
            "type":             item.get("type", "meeting"),
            "date":             item.get("date"),
            "time":             item.get("time"),
            "note":             item.get("note", ""),
            "reminder_30_sent": 0,
            "reminder_15_sent": 0,
            "created_at":       datetime.now(IST).strftime("%Y-%m-%d %H:%M")
        }
        self.client.post(BASE, headers=self._headers(), json=payload)

    # ── Get today's items ─────────────────────────────────
    def get_today_items(self, now_ist: datetime) -> list:
        today = now_ist.strftime("%Y-%m-%d")
        r = self.client.get(
            BASE,
            headers=self._headers(),
            params={"date": f"eq.{today}", "order": "time.asc"}
        )
        return r.json() if r.status_code == 200 else []

    # ── Get tomorrow's items ──────────────────────────────
    def get_tomorrow_items(self, now_ist: datetime) -> list:
        tomorrow = (now_ist + timedelta(days=1)).strftime("%Y-%m-%d")
        r = self.client.get(
            BASE,
            headers=self._headers(),
            params={"date": f"eq.{tomorrow}", "order": "time.asc"}
        )
        return r.json() if r.status_code == 200 else []

    # ── Get all upcoming items ────────────────────────────
    def get_upcoming_items(self, now_ist: datetime) -> list:
        today = now_ist.strftime("%Y-%m-%d")
        r = self.client.get(
            BASE,
            headers=self._headers(),
            params={"date": f"gte.{today}", "order": "date.asc,time.asc"}
        )
        return r.json() if r.status_code == 200 else []

    # ── Get items needing a reminder ──────────────────────
    def get_items_needing_reminder(self, now_ist: datetime) -> list:
        today = now_ist.strftime("%Y-%m-%d")
        r = self.client.get(
            BASE,
            headers=self._headers(),
            params={
                "date":   f"eq.{today}",
                "time":   "not.is.null",
                "order":  "time.asc",
                "or":     "(reminder_30_sent.eq.0,reminder_15_sent.eq.0)"
            }
        )
        return r.json() if r.status_code == 200 else []

    # ── Mark reminder as sent ─────────────────────────────
    def mark_reminder_sent(self, item_id: int, reminder_type: str):
        field = "reminder_30_sent" if reminder_type == "30min" else "reminder_15_sent"
        self.client.patch(
            BASE,
            headers=self._headers(),
            params={"id": f"eq.{item_id}"},
            json={field: 1}
        )

    # ── Delete item by title hint ─────────────────────────
    def delete_item_by_hint(self, hint: str) -> str | None:
        # Find matching item first
        r = self.client.get(
            BASE,
            headers=self._headers(),
            params={"title": f"ilike.*{hint}*", "limit": "1"}
        )
        items = r.json() if r.status_code == 200 else []
        if not items:
            return None

        item = items[0]
        self.client.delete(
            BASE,
            headers=self._headers(),
            params={"id": f"eq.{item['id']}"}
        )
        return item["title"]

    # ── Delete by exact ID ────────────────────────────────
    def delete_by_id(self, item_id: int):
        self.client.delete(
            BASE,
            headers=self._headers(),
            params={"id": f"eq.{item_id}"}
        )

    # ── Clear all items ───────────────────────────────────
    def clear_all(self):
        self.client.delete(
            BASE,
            headers=self._headers(),
            params={"id": "gte.0"}
        )
