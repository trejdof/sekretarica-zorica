# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-user Telegram bot running on a Raspberry Pi (systemd service: `zorica`). It acts as a personal secretary with two services: a media downloader and a Claude session scheduler.

## Running the bot

```bash
venv/bin/python bot.py
```

For the gallery web app separately:
```bash
venv/bin/python gallery/app.py
```

Manage the systemd service:
```bash
sudo systemctl restart zorica
sudo journalctl -u zorica -f
```

## Environment

Requires a `.env` file (see `.env.example`):
- `TELEGRAM_TOKEN` — Telegram bot token
- `ALLOWED_USER_ID` — single authorized Telegram user ID (all handlers use `user_filter` to enforce this)
- `GALLERY_SECRET` — token for gallery web auth (passed as `?t=` query param, then stored in cookie `gt`)
- `GALLERY_URL` — base URL where the gallery is hosted
- `MEDIA_DIR` — optional, defaults to `./media/`

## Architecture

`bot.py` wires everything together: it builds the PTB application, passes a `user_filter` (`filters.User(ALLOWED_USER_ID)`) to each service's `register()` call, and starts polling.

### Service pattern

Each service is a directory with:
- `handler.py` — registers PTB handlers via `register(app, user_filter)`
- `service.py` — core logic, no Telegram coupling

### downloader

Handles text messages with URLs, photos, and video uploads sent to the bot.

- **Instagram** — uses `instaloader` directly (handles image/video carousels; prompts for item index when multiple items exist)
- **Twitter/X** — uses `yt-dlp`
- **Direct image URLs** — downloaded and saved to `media/images/`
- **`/instacookie <sessionid>`** — updates `cookies.txt` (Netscape format) with a fresh Instagram session cookie

Media is saved to `MEDIA_DIR` (videos as `<id>.mp4` + `<id>.jpg` thumbnail + `<id>.json` metadata) or `MEDIA_DIR/images/` for images. Each file has a companion `.json` with `{id, type, original_url, source, downloaded_at, ...}`.

### claude_session_scheduler

Runs `claude --print` via subprocess on a cron schedule defined in `claude_session_scheduler/schedule.yaml`. Reports estimated session expiry (run time + 5h) back via Telegram.

- **`/jobs`** — list enabled jobs
- **`/run <job_name>`** — manually trigger a job

Jobs use APScheduler's `CronTrigger` registered into PTB's job queue.

### gallery

A Flask web app (`gallery/app.py`) for browsing and managing saved media. Auth is a shared secret passed as `?t=<GALLERY_SECRET>` (cookie-persisted for 30 days). Routes: `/` (videos), `/images`, `/v/<id>` (video detail), `/stream/<id>`, `/thumb/<id>`, `/download/<id>`, `/delete/<id>`.

## Adding a new service

1. Create `my_feature/` with `handler.py` (has `register(app, user_filter)`) and `service.py`
2. Import and register in `bot.py`:
   ```python
   from my_feature import handler as my_feature
   my_feature.register(app, user_filter)
   ```
