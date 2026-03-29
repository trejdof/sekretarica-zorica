import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, filters

import config
from downloader import handler as downloader
from downloader import cookie_handler
from claude_session_scheduler import handler as claude_session_scheduler
from claude_session_scheduler.service import register_jobs

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)

user_filter = filters.User(config.ALLOWED_USER_ID)


def main():
    app = ApplicationBuilder().token(config.TELEGRAM_TOKEN).build()

    downloader.register(app, user_filter)
    cookie_handler.register(app, user_filter)
    claude_session_scheduler.register(app, user_filter)
    register_jobs(app, config.ALLOWED_USER_ID)

    logging.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
