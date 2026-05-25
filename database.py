import sqlite3
import json
from datetime import datetime, timedelta
import pytz

IST = pytz.timezone("Asia/Kolkata")
DB_FILE = "assistant.db"

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                title               TEXT NOT NULL,
                type                TEXT NOT NULL DEFAULT 'meeting',  -- 'meeting' or 'task'
                date                TEXT,          -- YYYY-MM-DD
                time                TEXT,          -- HH:MM  (24h)
                note                TEXT,
                reminder_30_sent    INTEGER DEFAULT 0,
                reminder_15_sent    INTEGER DEFAULT 0,
                created_at          TEXT
            )
        """)
        self.conn.commit()

    # ── Save a new item ───────────────────────────────────
    def save_item(self, item: dict):
        self.conn.execute("""
            INSERT INTO items (title, type, date, time, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            item.get("title", "Untitled"),
            item.get("type", "meeting"),
            item.get("date"),
            item.get("time"),
            item.get("note", ""),
            datetime.now(IST).strftime("%Y-%m-%d %H:%M")
        ))
        self.conn.commit()

    # ── Get today's items ─────────────────────────────────
    def get_today_items(self, now_ist: datetime) -> list:
        today = now_ist.strftime("%Y-%m-%d")
        rows = self.conn.execute(
            "SELECT * FROM items WHERE date = ? ORDER BY time ASC",
            (today,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Get tomorrow's items ──────────────────────────────
    def get_tomorrow_items(self, now_ist: datetime) -> list:
        tomorrow = (now_ist + timedelta(days=1)).strftime("%Y-%m-%d")
        rows = self.conn.execute(
            "SELECT * FROM items WHERE date = ? ORDER BY time ASC",
            (tomorrow,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Get all upcoming items (today onwards) ────────────
    def get_upcoming_items(self, now_ist: datetime) -> list:
        today = now_ist.strftime("%Y-%m-%d")
        rows = self.conn.execute(
            "SELECT * FROM items WHERE date >= ? ORDER BY date ASC, time ASC",
            (today,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Get items that need a reminder right now ──────────
    def get_items_needing_reminder(self, now_ist: datetime) -> list:
        today = now_ist.strftime("%Y-%m-%d")
        rows = self.conn.execute(
            """SELECT * FROM items
               WHERE date = ?
               AND time IS NOT NULL
               AND (reminder_30_sent = 0 OR reminder_15_sent = 0)
               ORDER BY time ASC""",
            (today,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Mark a reminder as sent ───────────────────────────
    def mark_reminder_sent(self, item_id: int, reminder_type: str):
        if reminder_type == "30min":
            self.conn.execute(
                "UPDATE items SET reminder_30_sent = 1 WHERE id = ?", (item_id,)
            )
        elif reminder_type == "15min":
            self.conn.execute(
                "UPDATE items SET reminder_15_sent = 1 WHERE id = ?", (item_id,)
            )
        self.conn.commit()

    # ── Delete item by title hint ─────────────────────────
    def delete_item_by_hint(self, hint: str) -> str | None:
        row = self.conn.execute(
            "SELECT * FROM items WHERE title LIKE ? LIMIT 1",
            (f"%{hint}%",)
        ).fetchone()
        if row:
            self.conn.execute("DELETE FROM items WHERE id = ?", (row["id"],))
            self.conn.commit()
            return row["title"]
        return None
