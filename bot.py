import logging
import asyncio
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from database import Database
from ai_handler import AIHandler
from scheduler import ReminderScheduler

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

# ── Load config from environment ─────────────────────────
import os
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
OPENROUTER_KEY   = os.environ["OPENROUTER_KEY"]
YOUR_CHAT_ID     = int(os.environ["YOUR_CHAT_ID"])   # your personal Telegram chat ID

# ── Init shared objects ───────────────────────────────────
db        = Database()
ai        = AIHandler(OPENROUTER_KEY)
scheduler = ReminderScheduler(db)

# ─────────────────────────────────────────────────────────
# /start command
# ─────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_CHAT_ID:
        return
    await update.message.reply_text(
        "👋 Hey! I'm your personal assistant.\n\n"
        "Just talk to me naturally:\n"
        "• *Meeting with client tomorrow at 3pm*\n"
        "• *Call doctor on Friday 11am*\n"
        "• *Remind me to send report by 5pm today*\n"
        "• *What's on my schedule today?*\n"
        "• *Show all my tasks*\n\n"
        "I'll remind you 30 min and 15 min before every meeting, "
        "and send you a daily summary at 10 PM 🕙",
        parse_mode="Markdown"
    )

# ─────────────────────────────────────────────────────────
# Handle every incoming text message
# ─────────────────────────────────────────────────────────
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # Only respond to YOUR messages
    if update.effective_user.id != YOUR_CHAT_ID:
        return

    user_text = update.message.text
    now_ist   = datetime.now(IST)

    # Ask AI to understand the message
    result = await ai.process_message(user_text, now_ist)

    action = result.get("action")

    # ── Save a new meeting/task ───────────────────────────
    if action == "save":
        item = result.get("item", {})
        db.save_item(item)
        reply = result.get("reply", "Got it! ✅")
        await update.message.reply_text(reply)

    # ── Show today's schedule ─────────────────────────────
    elif action == "show_today":
        items = db.get_today_items(now_ist)
        if not items:
            await update.message.reply_text("📭 Nothing scheduled for today!")
        else:
            lines = ["📅 *Today's schedule:*\n"]
            for it in items:
                emoji = "📌" if it["type"] == "task" else "🗓"
                time_str = it.get("time", "")
                lines.append(f"{emoji} {time_str}  {it['title']}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    # ── Show all upcoming items ───────────────────────────
    elif action == "show_all":
        items = db.get_upcoming_items(now_ist)
        if not items:
            await update.message.reply_text("📭 No upcoming meetings or tasks!")
        else:
            lines = ["📋 *All upcoming:*\n"]
            for it in items:
                emoji = "📌" if it["type"] == "task" else "🗓"
                date_str = it.get("date", "") + " " + it.get("time", "")
                lines.append(f"{emoji} {date_str.strip()}  {it['title']}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    # ── Delete an item ────────────────────────────────────
    elif action == "delete":
        title_hint = result.get("title_hint", "")
        deleted = db.delete_item_by_hint(title_hint)
        if deleted:
            await update.message.reply_text(f"🗑 Deleted: *{deleted}*", parse_mode="Markdown")
        else:
            await update.message.reply_text("Couldn't find that item to delete.")

    # ── General chat / unknown ────────────────────────────
    else:
        reply = result.get("reply", "I'm here! Tell me about a meeting or task to save.")
        await update.message.reply_text(reply)

# ─────────────────────────────────────────────────────────
# Send daily summary at 10 PM IST
# ─────────────────────────────────────────────────────────
async def send_daily_summary(app: Application):
    now_ist   = datetime.now(IST)
    tomorrow  = db.get_tomorrow_items(now_ist)
    today_done = db.get_today_items(now_ist)

    lines = ["🌙 *Daily Summary*\n"]

    if today_done:
        lines.append("*Today's items:*")
        for it in today_done:
            emoji = "📌" if it["type"] == "task" else "🗓"
            lines.append(f"  {emoji} {it.get('time','')}  {it['title']}")
        lines.append("")

    if tomorrow:
        lines.append("*Tomorrow:*")
        for it in tomorrow:
            emoji = "📌" if it["type"] == "task" else "🗓"
            lines.append(f"  {emoji} {it.get('time','')}  {it['title']}")
    else:
        lines.append("*Tomorrow:* Nothing scheduled yet 😌")

    await app.bot.send_message(
        chat_id=YOUR_CHAT_ID,
        text="\n".join(lines),
        parse_mode="Markdown"
    )

# ─────────────────────────────────────────────────────────
# Background loop: check reminders + daily summary
# ─────────────────────────────────────────────────────────
async def background_loop(app: Application):
    daily_summary_sent_date = None

    while True:
        now_ist = datetime.now(IST)

        # Check reminders (runs every 60 seconds)
        due = scheduler.get_due_reminders(now_ist)
        for item in due:
            msg = f"⏰ *Reminder:* {item['title']}\n🕐 {item['time']} today"
            await app.bot.send_message(
                chat_id=YOUR_CHAT_ID,
                text=msg,
                parse_mode="Markdown"
            )
            db.mark_reminder_sent(item["id"], item["reminder_type"])

        # Daily summary at 10 PM IST
        if now_ist.hour == 22 and now_ist.minute == 0:
            today_str = now_ist.strftime("%Y-%m-%d")
            if daily_summary_sent_date != today_str:
                daily_summary_sent_date = today_str
                await send_daily_summary(app)

        await asyncio.sleep(60)  # check every minute

# ─────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start background reminder loop
    async def post_init(application: Application):
        asyncio.create_task(background_loop(application))

    app.post_init = post_init

    logger.info("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
