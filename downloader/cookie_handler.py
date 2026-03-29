import os
import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

logger = logging.getLogger(__name__)

COOKIES_FILE = os.path.join(os.path.dirname(__file__), "..", "cookies.txt")


async def handle_instacookie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /instacookie <sessionid value>")
        return

    sessionid = context.args[0].strip()

    with open(COOKIES_FILE, "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write(f".instagram.com\tTRUE\t/\tTRUE\t9999999999\tsessionid\t{sessionid}\n")

    logger.info("Instagram sessionid updated")
    await update.message.reply_text("✅ Instagram cookie updated.")


def register(app, user_filter):
    app.add_handler(CommandHandler("instacookie", handle_instacookie, filters=user_filter))
