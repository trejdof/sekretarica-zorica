import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from claude_session_scheduler.service import load_jobs, run_claude

logger = logging.getLogger(__name__)


async def cmd_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all scheduled jobs."""
    jobs = load_jobs()
    if not jobs:
        await update.message.reply_text("No jobs configured.")
        return

    lines = []
    for j in jobs:
        lines.append(f"• *{j['name']}* `{j['schedule']}`\n  _{j['message']}_")
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually trigger a job by name: /run <job_name>"""
    if not context.args:
        await update.message.reply_text("Usage: /run <job_name>")
        return

    job_name = context.args[0]
    jobs = {j["name"]: j for j in load_jobs()}

    if job_name not in jobs:
        await update.message.reply_text(f"Unknown job: {job_name}")
        return

    msg = await update.message.reply_text(f"Running {job_name}...")
    try:
        expiry = run_claude(jobs[job_name]["message"])
        await msg.edit_text(f"Claude session started. Expires at {expiry}.")
    except Exception as e:
        logger.error("Manual run of %s failed: %s", job_name, e)
        await msg.edit_text(f"Failed: {e}")


def register(app, user_filter):
    app.add_handler(CommandHandler("jobs", cmd_jobs, filters=user_filter))
    app.add_handler(CommandHandler("run", cmd_run, filters=user_filter))
