import logging
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

SCHEDULE_FILE = Path(__file__).parent / "schedule.yaml"


def load_jobs() -> list[dict]:
    with open(SCHEDULE_FILE) as f:
        data = yaml.safe_load(f)
    return [j for j in data.get("jobs", []) if j.get("enabled", True)]


def run_claude(message: str) -> str:
    """Send message to claude --print, return estimated session expiry (now + 5h)."""
    result = subprocess.run(
        ["claude", "--print"],
        input=message,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    expiry = (datetime.now(timezone.utc) + timedelta(hours=5)).astimezone()
    return expiry.strftime("%H:%M")


def register_jobs(app, chat_id: int) -> None:
    """Register all enabled jobs with PTB's JobQueue using cron scheduling."""
    from apscheduler.triggers.cron import CronTrigger

    jobs = load_jobs()
    for job in jobs:
        name = job["name"]
        message = job["message"]
        trigger = CronTrigger.from_crontab(job["schedule"])

        async def callback(context, msg=message, job_name=name):
            try:
                expiry = run_claude(msg)
                await context.bot.send_message(chat_id=chat_id, text=f"Claude session started. Expires at {expiry}.")
            except Exception as e:
                logger.error("Job %s failed: %s", job_name, e)
                await context.bot.send_message(chat_id=chat_id, text=f"[{job_name}] failed: {e}")

        app.job_queue.run_custom(callback, {"trigger": trigger}, name=name)
        logger.info("Scheduled job: %s (%s)", name, job["schedule"])
