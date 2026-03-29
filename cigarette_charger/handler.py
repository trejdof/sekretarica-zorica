import logging
from datetime import datetime, timedelta

from apscheduler.triggers.date import DateTrigger
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from cigarette_charger import service

logger = logging.getLogger(__name__)

_chat_id: int = None


def _schedule_next_charge(app):
    """Schedule a one-shot job for the next cigarette charge."""
    status = service.get_status()
    if not status["day_started"]:
        return
    next_dt = status["next_charge_dt"]
    if next_dt <= datetime.now():
        return
    app.job_queue.run_once(
        _charge_notify,
        when=next_dt,
        name="cig_charge",
    )
    logger.info("Next cig charge notification scheduled for %s", next_dt.strftime("%H:%M"))


async def _charge_notify(context) -> None:
    """Fired when a new cigarette becomes available."""
    status = service.get_status()
    if not status["day_started"]:
        return
    text = "🚬 New cigarette available!\n\n" + service.format_status(status)
    await context.bot.send_message(chat_id=_chat_id, text=text)
    _schedule_next_charge(context.application)


async def cmd_cigs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = service.get_status()
    await update.message.reply_text(service.format_status(status))


async def cmd_smoke(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    success, result = service.smoke()
    if success:
        await update.message.reply_text(f"🚬 Smoked. {result} left.")
    else:
        await update.message.reply_text(f"⛔ {result}")


async def cmd_cigset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Usage: /cigset <interval|start|base> <value>")
        return

    key, value = context.args[0].lower(), context.args[1]
    try:
        if key == "interval":
            msg = service.set_interval(float(value))
            _reschedule_charge(context.application)
        elif key == "start":
            msg = service.set_start(value)
            _reschedule_charge(context.application)
        elif key == "base":
            msg = service.set_base(int(value))
        else:
            await update.message.reply_text(f"Unknown setting: {key}. Use interval, start, or base.")
            return
        await update.message.reply_text(f"✅ {msg}")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_cighelp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🚬 *Cigarette Charger*\n\n"
        "/cigs — current status\n"
        "/smoke — consume a cigarette\n"
        "/cigset interval <hours> — charge interval \\(e\\.g\\. `1\\.5`\\)\n"
        "/cigset start <HH:MM> — day start time \\(e\\.g\\. `08:00`\\)\n"
        "/cigset base <n> — cigarettes at day start\n"
        "/cighelp — show this help"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")


def _reschedule_charge(app):
    """Cancel existing charge job and schedule a fresh one."""
    current_jobs = app.job_queue.get_jobs_by_name("cig_charge")
    for job in current_jobs:
        job.schedule_removal()
    _schedule_next_charge(app)


def register(app, user_filter, chat_id: int):
    global _chat_id
    _chat_id = chat_id

    app.add_handler(CommandHandler("cigs", cmd_cigs, filters=user_filter))
    app.add_handler(CommandHandler("smoke", cmd_smoke, filters=user_filter))
    app.add_handler(CommandHandler("cigset", cmd_cigset, filters=user_filter))
    app.add_handler(CommandHandler("cighelp", cmd_cighelp, filters=user_filter))

    _schedule_next_charge(app)
