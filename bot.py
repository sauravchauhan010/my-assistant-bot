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

WEBHOOK_PATH = f"/webhook/{TELEGRAM_TOKEN}"
WEBHOOK_URL  = f"{RENDER_URL.rstrip('/')}{WEBHOOK_PATH}"

db        = Database()
ai        = AIHandler(OPENROUTER_KEY)
scheduler = ReminderScheduler(db)

# Temp store for delete confirmation: {chat_id: [list of items]}
pending_delete = {}

# ─────────────────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_CHAT_ID:
        return
    await update.message.reply_text(
        "👋 Hey! I'm your personal assistant.\n\n"
        "Just talk to me naturally or use commands:\n"
        "/today — today's schedule\n"
        "/all — all upcoming meetings\n"
        "/delete — delete a meeting\n"
        "/done — mark a task as done\n"
        "/clear — clear everything\n"
        "/summary — get daily summary now\n"
        "/help — show all commands\n\n"
        "Or just say: _Meeting with client tomorrow at 3pm_ 🎤",
        parse_mode="Markdown"
    )

# ─────────────────────────────────────────────────────────
# /help
# ─────────────────────────────────────────────────────────
async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_CHAT_ID:
        return
    await update.message.reply_text(
        "📖 *All Commands:*\n\n"
        "/today — show today's schedule\n"
        "/all — show all upcoming meetings & tasks\n"
        "/delete — pick and delete a meeting or task\n"
        "/done — mark a task as completed\n"
        "/clear — delete ALL meetings and tasks\n"
        "/summary — get your daily summary right now\n"
        "/help — show this message\n\n"
        "💬 Or just talk naturally — I understand plain English & Hindi too!",
        parse_mode="Markdown"
    )

# ─────────────────────────────────────────────────────────
# /today
# ─────────────────────────────────────────────────────────
async def today_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_CHAT_ID:
        return
    now_ist = datetime.now(IST)
    items   = db.get_today_items(now_ist)
    if not items:
        await update.message.reply_text("📭 Nothing scheduled for today!")
    else:
        lines = ["📅 *Today's schedule:*\n"]
        for i, it in enumerate(items, 1):
            emoji = "📌" if it["type"] == "task" else "🗓"
            lines.append(f"{i}. {emoji} {it.get('time','')}  {it['title']}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────────────────────
# /all
# ─────────────────────────────────────────────────────────
async def all_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_CHAT_ID:
        return
    now_ist = datetime.now(IST)
    items   = db.get_upcoming_items(now_ist)
    if not items:
        await update.message.reply_text("📭 No upcoming meetings or tasks!")
    else:
        lines = ["📋 *All upcoming:*\n"]
        for i, it in enumerate(items, 1):
            emoji    = "📌" if it["type"] == "task" else "🗓"
            date_str = f"{it.get('date','')} {it.get('time','')}".strip()
            lines.append(f"{i}. {emoji} {date_str}  {it['title']}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────────────────────
# /delete — show numbered list, wait for number reply
# ─────────────────────────────────────────────────────────
async def delete_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_CHAT_ID:
        return
    now_ist = datetime.now(IST)
    items   = db.get_upcoming_items(now_ist)
    if not items:
        await update.message.reply_text("📭 Nothing to delete!")
        return

    # Store list in memory for this user
    pending_delete[YOUR_CHAT_ID] = items

    lines = ["🗑 *Which one to delete?*\nReply with the number:\n"]
    for i, it in enumerate(items, 1):
        emoji    = "📌" if it["type"] == "task" else "🗓"
        date_str = f"{it.get('date','')} {it.get('time','')}".strip()
        lines.append(f"{i}. {emoji} {date_str}  {it['title']}")
    lines.append("\n0. Cancel")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────────────────────
# /done — mark task complete (shows list to pick from)
# ─────────────────────────────────────────────────────────
async def done_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_CHAT_ID:
        return
    now_ist = datetime.now(IST)
    items   = db.get_today_items(now_ist)
    if not items:
        await update.message.reply_text("📭 No tasks for today!")
        return

    pending_delete[YOUR_CHAT_ID] = items  # reuse same flow

    lines = ["✅ *Which task is done?*\nReply with the number:\n"]
    for i, it in enumerate(items, 1):
        emoji = "📌" if it["type"] == "task" else "🗓"
        lines.append(f"{i}. {emoji} {it.get('time','')}  {it['title']}")
    lines.append("\n0. Cancel")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────────────────────
# /clear — delete everything
# ─────────────────────────────────────────────────────────
async def clear_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_CHAT_ID:
        return
    db.clear_all()
    await update.message.reply_text("🗑 All meetings and tasks cleared!")

# ─────────────────────────────────────────────────────────
# /summary — send daily summary right now
# ─────────────────────────────────────────────────────────
async def summary_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_CHAT_ID:
        return
    await send_daily_summary(ctx.application)

# ─────────────────────────────────────────────────────────
# Handle text messages
# ─────────────────────────────────────────────────────────
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != YOUR_CHAT_ID:
        return

    text = update.message.text.strip()

    # Check if user is replying with a number for delete/done
    if YOUR_CHAT_ID in pending_delete and text.isdigit():
        items = pending_delete[YOUR_CHAT_ID]
        num   = int(text)

        if num == 0:
            del pending_delete[YOUR_CHAT_ID]
            await update.message.reply_text("Cancelled. ✅")
            return

        if 1 <= num <= len(items):
            item = items[num - 1]
            db.delete_by_id(item["id"])
            del pending_delete[YOUR_CHAT_ID]
            emoji = "📌" if item["type"] == "task" else "🗓"
            await update.message.reply_text(
                f"✅ Removed: {emoji} *{item['title']}*",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"Please reply with a number between 1 and {len(items)}, or 0 to cancel.")
        return

    # Normal message — process with AI
    await process_and_reply(update, text, datetime.now(IST))

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
# Core: process text and reply
# ─────────────────────────────────────────────────────────
async def process_and_reply(update: Update, user_text: str, now_ist: datetime):
    result = await ai.process_message(user_text, now_ist)
    action = result.get("action")

    if action == "save":
        db.save_item(result.get("item", {}))
        await update.message.reply_text(result.get("reply", "Got it! ✅"))

    elif action == "show_today":
        items = db.get_today_items(now_ist)
        if not items:
            await update.message.reply_text("📭 Nothing scheduled for today!")
        else:
            lines = ["📅 *Today's schedule:*\n"]
            for i, it in enumerate(items, 1):
                emoji = "📌" if it["type"] == "task" else "🗓"
                lines.append(f"{i}. {emoji} {it.get('time','')}  {it['title']}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    elif action == "show_all":
        items = db.get_upcoming_items(now_ist)
        if not items:
            await update.message.reply_text("📭 No upcoming meetings or tasks!")
        else:
            lines = ["📋 *All upcoming:*\n"]
            for i, it in enumerate(items, 1):
                emoji    = "📌" if it["type"] == "task" else "🗓"
                date_str = f"{it.get('date','')} {it.get('time','')}".strip()
                lines.append(f"{i}. {emoji} {date_str}  {it['title']}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    elif action == "delete":
        # AI-detected delete — fall back to list method
        await delete_cmd(update, None)

    else:
        await update.message.reply_text(result.get("reply", "I'm here! Tell me about a meeting or task."))

# ─────────────────────────────────────────────────────────
# Daily summary
# ─────────────────────────────────────────────────────────
async def send_daily_summary(app: Application):
    now_ist  = datetime.now(IST)
    today    = db.get_today_items(now_ist)
    tomorrow = db.get_tomorrow_items(now_ist)
    lines    = ["🌙 *Daily Summary*\n"]

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
# Background loop
# ─────────────────────────────────────────────────────────
async def background_loop(app: Application):
    daily_summary_sent_date = None
    while True:
        try:
            now_ist = datetime.now(IST)

            for item in scheduler.get_due_reminders(now_ist):
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
                db.mark_reminder_sent(item["id"], item["reminder_type"])

            if now_ist.hour == 22 and now_ist.minute == 0:
                today_str = now_ist.strftime("%Y-%m-%d")
                if daily_summary_sent_date != today_str:
                    daily_summary_sent_date = today_str
                    await send_daily_summary(app)

        except Exception as e:
            logger.error(f"Background loop error: {e}")

        await asyncio.sleep(60)

# ─────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────
async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("help",    help_cmd))
    app.add_handler(CommandHandler("today",   today_cmd))
    app.add_handler(CommandHandler("all",     all_cmd))
    app.add_handler(CommandHandler("delete",  delete_cmd))
    app.add_handler(CommandHandler("done",    done_cmd))
    app.add_handler(CommandHandler("clear",   clear_cmd))
    app.add_handler(CommandHandler("summary", summary_cmd))
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
