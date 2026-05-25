from datetime import datetime
import pytz
from database import Database

IST = pytz.timezone("Asia/Kolkata")

class ReminderScheduler:
    def __init__(self, db: Database):
        self.db = db

    async def get_due_reminders(self, now_ist: datetime) -> list:
        """
        Returns list of items that need a reminder sent RIGHT NOW.
        Each item gets a 'reminder_type' key: '30min' or '15min'
        """
        due = []
        items = await self.db.get_items_needing_reminder(now_ist)

        for item in items:
            if not item.get("time"):
                continue

            try:
                item_dt_str = f"{item['date']} {item['time']}"
                item_dt     = IST.localize(
                    datetime.strptime(item_dt_str, "%Y-%m-%d %H:%M")
                )
            except Exception:
                continue

            minutes_until = (item_dt - now_ist).total_seconds() / 60

            # 30-min reminder: fire between 29 and 31 minutes before
            if 29 <= minutes_until <= 31 and not item["reminder_30_sent"]:
                due.append({**item, "reminder_type": "30min"})

            # 15-min reminder: fire between 14 and 16 minutes before
            elif 14 <= minutes_until <= 16 and not item["reminder_15_sent"]:
                due.append({**item, "reminder_type": "15min"})

        return due
