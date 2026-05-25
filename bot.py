import logging
import asyncio
import os
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from aiohttp import web
from database import Database
from ai_handler import AIHandler
from scheduler import ReminderScheduler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENROUTER_KEY = os.environ["OPENROUTER_KEY"]
YOUR_CHAT_ID   = int(os.environ["YOUR_CHAT_ID"])
RENDER_URL     = os.environ["RENDER_URL"]
PORT           = int(os.environ.get("PORT", 8080))

WEBHOOK_PATH   = f"/webhook/{TELEGRAM_TOKEN}"
WEBHOOK_URL    = f"{RENDER_URL.rstrip('/')}{WEBHOOK_PATH}"

db        = Database()
ai        = AIHandler(OPENROUTER_KEY)
scheduler = ReminderScheduler(db)

# ─────────────────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_CHAT_ID:
        return
    await update.message.reply_text(
        "👋 Hey! I'm your personal assistant.\n\n"
        "Talk to me naturally or send a 🎤 voice message:\n"
        "• *Meeting with client tomorrow at 3pm*\n"
        "• *Call doctor on Friday 11am*\n"
        "• *What's on my schedule today?*\n"
        "• *Show all my tasks*\n\n"
        "I'll remind you 30 min and 15 min before every meeting "
        "and send a daily summary at 10 PM 🕙",
        parse_mode="Markdown"
    )

# ─────────────────────────────────────────────────────────
# Handle text messages
# ─────────────────────────────────────────────────────────
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_CHAT_ID:
        return
    await process_and_reply(update, update.message.text, datetime.now(IST))

# ─────────────────────────────────────────────────────────
# Handle voice messages
# ─────────────────────────────────────────────────────────
async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_CHAT_ID:
        return

    await update.message.reply_text("🎤 Got your voice note, transcribing...")

    try:
        voice_file  = await ctx.bot.get_file(update.message.voice.file_id)
        voice_bytes = await voice_file.download_as_bytearray()
        text        = await ai.transcribe_voice(bytes(voice_bytes))

        if not text:
            await update.message.reply_text("Sorry, couldn't understand. Please try again.")
            return

        await update.message.reply_text(f"📝 I heard: _{text}_", parse_mode="Markdown")
        await process_and_reply(update, text, datetime.now(IST))

    except Exception as e:
        logger.error(f"Voice error: {e}")
        await update.message.reply_text("Sorry, voice processing failed. Try typing instead.")

# ─────────────────────────────────────────────────────────
# Core logic — process message and reply
# ─────────────────────────────────────────────────────────
async def process_and_reply(update: Update, user_text: str, now_ist: datetime):
    result = await ai.process_message(user_text, now_ist)
    action = result.get("action")

    if action == "save":
        await db.save_item(result.get("item", {}))  # FIX: was missing await
        await update.message.reply_text(result.get("reply", "Got it! ✅"))

    elif action == "show_today":
        items = await db.get_today_items(now_ist)  # FIX: was missing await
        if not items:
            await update.message.reply_text("📭 Nothing scheduled for today!")
        else:
            lines = ["📅 *Today's schedule:*\n"]
            for i, it in enumerate(items, 1):
                emoji = "📌" if it["type"] == "task" else "🗓"
                time_str = it.get("time", "")
                lines.append(f"{i}. {emoji} {time_str}  {it['title']}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    elif action == "show_all":
        items = await db.get_upcoming_items(now_ist)  # FIX: was missing await
        if not items:
            await update.message.reply_text("📭 No upcoming meetings or tasks!")
        else:
            lines = ["📋 *All upcoming:*\n"]
            for i, it in enumerate(items, 1):
                emoji    = "📌" if it["type"] == "task" else "🗓"
                date_str = f"{it.get('date','')} {it.get('time','')}" .strip()
                lines.append(f"{i}. {emoji} {date_str}  {it['title']}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    elif action == "delete":
        deleted = await db.delete_item_by_hint(result.get("title_hint", ""))  # FIX: was missing await
        if deleted:
            await update.message.reply_text(f"🗑 Deleted: *{deleted}*", parse_mode="Markdown")
        else:
            await update.message.reply_text("Couldn't find that item to delete.")

    else:
        await update.message.reply_text(result.get("reply", "I'm here! Tell me about a meeting or task."))

# ─────────────────────────────────────────────────────────
# Daily summary at 10 PM IST
# ─────────────────────────────────────────────────────────
async def send_daily_summary(app: Application):
    now_ist    = datetime.now(IST)
    today      = await db.get_today_items(now_ist)    # FIX: was missing await
    tomorrow   = await db.get_tomorrow_items(now_ist) # FIX: was missing await
    lines      = ["🌙 *Daily Summary*\n"]

    if today:
        lines.append("*Today's items:*")
        for i, it in enumerate(today, 1):
            emoji = "📌" if it["type"] == "task" else "🗓"
            lines.append(f"  {i}. {emoji} {it.get('time','')}  {it['title']}")
        lines.append("")

    if tomorrow:
        lines.append("*Tomorrow:*")
        for i, it in enumerate(tomorrow, 1):
            emoji = "📌" if it["type"] == "task" else "🗓"
            lines.append(f"  {i}. {emoji} {it.get('time','')}  {it['title']}")
    else:
        lines.append("*Tomorrow:* Nothing scheduled yet 😌")

    await app.bot.send_message(
        chat_id=YOUR_CHAT_ID,
        text="\n".join(lines),
        parse_mode="Markdown"
    )

# ─────────────────────────────────────────────────────────
# Background loop — reminders every 60s + daily summary
# ─────────────────────────────────────────────────────────
async def background_loop(app: Application):
    daily_summary_sent_date = None

    while True:
        try:
            now_ist = datetime.now(IST)

            for item in await scheduler.get_due_reminders(now_ist):  # FIX: was missing await
                mins  = "30 minutes" if item["reminder_type"] == "30min" else "15 minutes"
                emoji = "📌" if item["type"] == "task" else "🗓"
                msg   = (
                    f"⏰ *Reminder — {mins} to go!*\n\n"
                    f"{emoji} *{item['title']}*\n"
                    f"🕐 Scheduled at {item['time']} today"
                )
                await app.bot.send_message(
                    chat_id=YOUR_CHAT_ID,
                    text=msg,
                    parse_mode="Markdown"
                )
                await db.mark_reminder_sent(item["id"], item["reminder_type"])  # FIX: was missing await

            # FIX: widened window to minute < 5 so a loop hiccup can't skip the summary
            if now_ist.hour == 22 and now_ist.minute < 5:
                today_str = now_ist.strftime("%Y-%m-%d")
                if daily_summary_sent_date != today_str:
                    daily_summary_sent_date = today_str
                    await send_daily_summary(app)

        except Exception as e:
            logger.error(f"Background loop error: {e}")

        await asyncio.sleep(60)

# ─────────────────────────────────────────────────────────
# Main — webhook + HTTP server
# ─────────────────────────────────────────────────────────
async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    async def health(request):
        return web.Response(text="OK")

    async def webhook(request):
        data   = await request.json()
        update = Update.de_json(data, app.bot)
        await app.process_update(update)
        return web.Response(text="OK")

    web_app = web.Application()
    web_app.router.add_get("/", health)
    web_app.router.add_post(WEBHOOK_PATH, webhook)

    async with app:
        await app.initialize()
        await app.bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"Webhook set: {WEBHOOK_URL}")

        asyncio.create_task(background_loop(app))

        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()
        logger.info(f"Server running on port {PORT}")

        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
