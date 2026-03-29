import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone

import requests
import yt_dlp

import config

logger = logging.getLogger(__name__)

SUPPORTED_DOMAINS = (
    "instagram.com",
    "twitter.com",
    "x.com",
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
IMAGE_DIR = os.path.join(config.MEDIA_DIR, "images")
os.makedirs(IMAGE_DIR, exist_ok=True)

_INSTALOADER_SHORTCODE_RE = re.compile(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)")


def is_supported_url(url: str) -> bool:
    return any(domain in url for domain in SUPPORTED_DOMAINS) or is_direct_image_url(url)


def is_direct_image_url(url: str) -> bool:
    path = url.split("?")[0].lower()
    return any(path.endswith(ext) for ext in IMAGE_EXTENSIONS)


def _source(url: str) -> str:
    if "instagram.com" in url:
        return "Instagram"
    if "twitter.com" in url or "x.com" in url:
        return "X / Twitter"
    return "Direct"


def _cookies_file():
    return os.path.join(os.path.dirname(__file__), "..", "cookies.txt")


def _get_instagram_sessionid() -> str | None:
    cf = _cookies_file()
    if not os.path.exists(cf):
        return None
    with open(cf) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7 and parts[5] == "sessionid":
                return parts[6]
    return None


def _make_instaloader():
    import instaloader
    L = instaloader.Instaloader(
        download_pictures=True,
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        post_metadata_txt_pattern="",
        quiet=True,
    )
    sessionid = _get_instagram_sessionid()
    if sessionid:
        L.context._session.cookies.set("sessionid", sessionid, domain=".instagram.com")
    return L


def _generate_thumb(video_path: str, thumb_path: str):
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-ss", "00:00:01",
         "-vframes", "1", "-vf", "scale=480:-1", thumb_path],
        capture_output=True,
    )


def _save_media_url(media_url: str, original_url: str, is_video: bool, media_id: str) -> dict:
    """Download a CDN URL and save it as image or video."""
    resp = requests.get(media_url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()

    if is_video:
        final_path = os.path.join(config.MEDIA_DIR, media_id + ".mp4")
        with open(final_path, "wb") as f:
            f.write(resp.content)
        thumb_path = os.path.join(config.MEDIA_DIR, media_id + ".jpg")
        _generate_thumb(final_path, thumb_path)
        has_thumb = os.path.exists(thumb_path)
        size_mb = round(os.path.getsize(final_path) / 1024 / 1024, 1)
        meta = {
            "id": media_id,
            "type": "video",
            "original_url": original_url,
            "source": "Instagram",
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "has_thumb": has_thumb,
        }
        with open(os.path.join(config.MEDIA_DIR, media_id + ".json"), "w") as f:
            json.dump(meta, f)
        logger.info("Saved Instagram video %s — %.1f MB", media_id, size_mb)
    else:
        content_type = resp.headers.get("content-type", "")
        ext = ".png" if "png" in content_type else ".webp" if "webp" in content_type else ".jpg"
        final_path = os.path.join(IMAGE_DIR, media_id + ext)
        with open(final_path, "wb") as f:
            f.write(resp.content)
        size_kb = round(os.path.getsize(final_path) / 1024, 1)
        meta = {
            "id": media_id,
            "type": "image",
            "original_url": original_url,
            "source": "Instagram",
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "file_ext": ext,
            "size_kb": size_kb,
        }
        with open(os.path.join(IMAGE_DIR, media_id + ".json"), "w") as f:
            json.dump(meta, f)
        logger.info("Saved Instagram image %s — %.1f KB", media_id, size_kb)

    return meta


def get_instagram_carousel_count(url: str) -> int:
    """Return number of items in an Instagram post (1 if not a carousel)."""
    import instaloader
    m = _INSTALOADER_SHORTCODE_RE.search(url)
    if not m:
        return 1
    shortcode = m.group(1)
    try:
        L = _make_instaloader()
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        if post.typename == "GraphSidecar":
            return len(list(post.get_sidecar_nodes()))
        return 1
    except Exception as e:
        logger.warning("Could not get carousel count for %s: %s", url, e)
        return 1


def _save_with_instaloader(url: str, item_index: int = None) -> dict:
    """Download Instagram post using instaloader (handles image carousels)."""
    import instaloader
    m = _INSTALOADER_SHORTCODE_RE.search(url)
    if not m:
        raise ValueError("Cannot extract Instagram shortcode from URL")
    shortcode = m.group(1)

    L = _make_instaloader()
    post = instaloader.Post.from_shortcode(L.context, shortcode)

    if post.typename == "GraphSidecar":
        nodes = list(post.get_sidecar_nodes())
        if item_index is None:
            node = nodes[0]
            idx_suffix = "_1"
        else:
            node = nodes[item_index - 1]
            idx_suffix = f"_{item_index}"
        media_id = shortcode + idx_suffix
        cdn_url = node.video_url if node.is_video else node.display_url
        return _save_media_url(cdn_url, url, node.is_video, media_id)
    else:
        media_id = shortcode
        cdn_url = post.video_url if post.is_video else post.url
        return _save_media_url(cdn_url, url, post.is_video, media_id)


def save_video_from_file(tmp_path: str, source: str = "Telegram") -> dict:
    """Move a temp video file into MEDIA_DIR, generate thumb, save metadata."""
    media_id = uuid.uuid4().hex[:16]
    final_path = os.path.join(config.MEDIA_DIR, media_id + ".mp4")
    shutil.move(tmp_path, final_path)

    thumb_path = os.path.join(config.MEDIA_DIR, media_id + ".jpg")
    _generate_thumb(final_path, thumb_path)
    has_thumb = os.path.exists(thumb_path)

    size_mb = round(os.path.getsize(final_path) / 1024 / 1024, 1)
    logger.info("Saved video from file %s — %.1f MB", media_id, size_mb)

    meta = {
        "id": media_id,
        "type": "video",
        "original_url": "",
        "source": source,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "has_thumb": has_thumb,
    }
    with open(os.path.join(config.MEDIA_DIR, media_id + ".json"), "w") as f:
        json.dump(meta, f)

    return meta


def save_image_from_url(url: str) -> dict:
    """Download a direct image URL and save to IMAGE_DIR."""
    resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    if "png" in content_type:
        ext = ".png"
    elif "gif" in content_type:
        ext = ".gif"
    elif "webp" in content_type:
        ext = ".webp"
    else:
        ext = ".jpg"

    image_id = hashlib.md5(url.encode()).hexdigest()[:16]
    final_path = os.path.join(IMAGE_DIR, image_id + ext)
    with open(final_path, "wb") as f:
        f.write(resp.content)

    size_kb = round(os.path.getsize(final_path) / 1024, 1)
    logger.info("Downloaded image %s — %.1f KB", image_id, size_kb)

    meta = {
        "id": image_id,
        "type": "image",
        "original_url": url,
        "source": _source(url),
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "file_ext": ext,
        "size_kb": size_kb,
    }
    with open(os.path.join(IMAGE_DIR, image_id + ".json"), "w") as f:
        json.dump(meta, f)

    return meta


def save_image_from_bytes(file_bytes: bytes, file_ext: str, original_url: str = "", source: str = "Telegram") -> dict:
    """Save image from raw bytes (e.g. Telegram photo)."""
    if not file_ext.startswith("."):
        file_ext = "." + file_ext

    image_id = uuid.uuid4().hex[:16]
    final_path = os.path.join(IMAGE_DIR, image_id + file_ext)
    with open(final_path, "wb") as f:
        f.write(file_bytes)

    size_kb = round(os.path.getsize(final_path) / 1024, 1)
    logger.info("Saved image from bytes %s — %.1f KB", image_id, size_kb)

    meta = {
        "id": image_id,
        "type": "image",
        "original_url": original_url,
        "source": source,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "file_ext": file_ext,
        "size_kb": size_kb,
    }
    with open(os.path.join(IMAGE_DIR, image_id + ".json"), "w") as f:
        json.dump(meta, f)

    return meta


def save_video(url: str, item_index: int = None) -> dict:
    """Download video (or image) via yt-dlp, falling back to instaloader for Instagram. Returns metadata dict."""
    # For Instagram, use instaloader directly — it correctly identifies image vs video carousels
    if "instagram.com" in url:
        return _save_with_instaloader(url, item_index)

    tmp_dir = tempfile.mkdtemp()
    output_template = os.path.join(tmp_dir, "%(id)s.%(ext)s")

    cookies_file = _cookies_file()
    cookies_path = cookies_file if os.path.exists(cookies_file) else None
    ydl_opts = {
        "outtmpl": output_template,
        "format": "bestvideo+bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "cookiefile": cookies_path,
    }

    if item_index is not None:
        ydl_opts["playlist_items"] = str(item_index)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    files = os.listdir(tmp_dir)
    if not files:
        raise RuntimeError("Download produced no files")

    tmp_path = os.path.join(tmp_dir, files[0])
    parts = files[0].rsplit(".", 1)
    media_id = parts[0]
    file_ext = ("." + parts[1].lower()) if len(parts) > 1 else ".mp4"
    logger.info("Downloaded %s — %.1f MB", files[0], os.path.getsize(tmp_path) / 1024 / 1024)

    if file_ext in IMAGE_EXTENSIONS:
        final_path = os.path.join(IMAGE_DIR, media_id + file_ext)
        shutil.move(tmp_path, final_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)

        size_kb = round(os.path.getsize(final_path) / 1024, 1)
        meta = {
            "id": media_id,
            "type": "image",
            "original_url": url,
            "source": _source(url),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "file_ext": file_ext,
            "size_kb": size_kb,
        }
        with open(os.path.join(IMAGE_DIR, media_id + ".json"), "w") as f:
            json.dump(meta, f)
        return meta

    final_path = os.path.join(config.MEDIA_DIR, media_id + ".mp4")
    shutil.move(tmp_path, final_path)
    shutil.rmtree(tmp_dir, ignore_errors=True)

    thumb_path = os.path.join(config.MEDIA_DIR, media_id + ".jpg")
    _generate_thumb(final_path, thumb_path)
    has_thumb = os.path.exists(thumb_path)

    meta = {
        "id": media_id,
        "type": "video",
        "original_url": url,
        "source": _source(url),
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "has_thumb": has_thumb,
    }
    with open(os.path.join(config.MEDIA_DIR, media_id + ".json"), "w") as f:
        json.dump(meta, f)

    return meta
