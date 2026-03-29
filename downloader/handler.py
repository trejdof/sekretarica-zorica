import logging
import re
import tempfile

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

import config
from downloader.service import (
    get_instagram_carousel_count,
    is_direct_image_url,
    is_supported_url,
    save_image_from_bytes,
    save_image_from_url,
    save_video,
    save_video_from_file,
)

logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r"https?://\S+")
CAROUSEL_KEY = "carousel_pending"


def _gallery_url(meta: dict) -> str:
    if meta.get("type") == "image":
        return f"{config.GALLERY_URL}/images?t={config.GALLERY_SECRET}"
    return f"{config.GALLERY_URL}/?t={config.GALLERY_SECRET}"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""

    # Respond to carousel item selection
    if CAROUSEL_KEY in context.user_data:
        pending = context.user_data.pop(CAROUSEL_KEY)
        url, count = pending["url"], pending["count"]

        if text.strip().isdigit():
            idx = int(text.strip())
            if 1 <= idx <= count:
                msg = await update.message.reply_text(f"Downloading item {idx}/{count}...")
                try:
                    meta = save_video(url, item_index=idx)
                    await msg.edit_text(f"✅ Ready: {_gallery_url(meta)}")
                except Exception as e:
                    logger.error("Download failed for %s item %s: %s", url, idx, e)
                    await msg.edit_text(f"Failed: {e}")
                return
            else:
                await update.message.reply_text(f"Please send a number between 1 and {count}.")
                context.user_data[CAROUSEL_KEY] = pending
                return
        else:
            await update.message.reply_text("Cancelled.")
            return

    urls = URL_PATTERN.findall(text)
    supported = [u for u in urls if is_supported_url(u)]

    if not supported:
        return

    url = supported[0]

    # Direct image URL
    if is_direct_image_url(url):
        msg = await update.message.reply_text("Downloading image...")
        try:
            meta = save_image_from_url(url)
            await msg.edit_text(f"✅ Image saved: {_gallery_url(meta)}")
        except Exception as e:
            logger.error("Image download failed for %s: %s", url, e)
            await msg.edit_text(f"Failed: {e}")
        return

    # Instagram carousel check
    if "instagram.com" in url:
        msg = await update.message.reply_text("Checking post...")
        try:
            count = get_instagram_carousel_count(url)
            if count > 1:
                context.user_data[CAROUSEL_KEY] = {"url": url, "count": count}
                await msg.edit_text(
                    f"This post has {count} items. Which one do you want to download? (1–{count})"
                )
                return
            await msg.edit_text("Downloading...")
        except Exception as e:
            logger.warning("Carousel check failed for %s: %s — trying download anyway", url, e)
            await msg.edit_text("Downloading...")
    else:
        msg = await update.message.reply_text("Downloading...")

    try:
        meta = save_video(url)
        await msg.edit_text(f"✅ Ready: {_gallery_url(meta)}")
    except Exception as e:
        logger.error("Download failed for %s: %s", url, e)
        await msg.edit_text(f"Failed: {e}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save photo sent directly to the bot."""
    photo = update.message.photo[-1]  # largest available size
    msg = await update.message.reply_text("Saving image...")
    try:
        tg_file = await context.bot.get_file(photo.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        meta = save_image_from_bytes(bytes(file_bytes), ".jpg", source="Telegram")
        await msg.edit_text(f"✅ Image saved: {_gallery_url(meta)}")
    except Exception as e:
        logger.error("Photo save failed: %s", e)
        await msg.edit_text(f"Failed: {e}")


async def handle_video_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save video or video document sent directly to the bot."""
    msg = update.message
    file_obj = msg.video or (msg.document if msg.document and (msg.document.mime_type or "").startswith("video/") else None)
    if not file_obj:
        return

    reply = await msg.reply_text("Saving video...")
    try:
        tg_file = await context.bot.get_file(file_obj.file_id)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp_path = tmp.name
        await tg_file.download_to_drive(tmp_path)
        meta = save_video_from_file(tmp_path)
        await reply.edit_text(f"✅ Video saved: {_gallery_url(meta)}")
    except Exception as e:
        logger.error("Video upload failed: %s", e)
        await reply.edit_text(f"Failed: {e}")


def register(app, user_filter):
    app.add_handler(MessageHandler(user_filter & filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(user_filter & filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(user_filter & (filters.VIDEO | filters.Document.VIDEO), handle_video_upload))
