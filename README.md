# sekretarica-zorica

A personal Telegram bot running on a Raspberry Pi, acting as a secretary for daily tasks.
Only responds to a single authorized user.

## Services

### downloader
Detects Instagram and Twitter/X URLs in messages and sends the video back for easy downloading.

**Usage:** Just send a link — the bot replies with the video file.

**Supported sites:** Instagram, Twitter/X (anything `yt-dlp` can handle from those domains)

---

### claude_session_scheduler
Runs scheduled prompts through the Claude CLI and reports back via Telegram.
Used to kick off a Claude session each morning and track when it expires.

**Usage:**
- `/jobs` — list all scheduled jobs with their cron schedule and prompt
- `/run <job_name>` — manually trigger a job

After a job runs, the bot sends: `Claude session started. Expires at HH:MM.` (estimated as time of run + 5 hours).

**Config:** `claude_session_scheduler/schedule.yaml`

```yaml
jobs:
  - name: morning_session_start
    schedule: "0 8 * * *"   # every day at 08:00
    message: "Hi"
    enabled: true
```

---

## Setup

**Requirements:** Python 3.11+, `ffmpeg`, `claude` CLI authenticated

```bash
git clone <repo>
cd sekretarica-zorica
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```
TELEGRAM_TOKEN=your_bot_token_here
ALLOWED_USER_ID=your_telegram_user_id
```

- Get a bot token from [@BotFather](https://t.me/BotFather)
- Get your user ID from [@userinfobot](https://t.me/userinfobot)

**Run manually:**

```bash
venv/bin/python bot.py
```

**Run as a systemd service (recommended):**

```bash
sudo nano /etc/systemd/system/zorica.service
```

```ini
[Unit]
Description=Zorica Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=dietpi
WorkingDirectory=/home/dietpi/sekretarica-zorica
ExecStart=/home/dietpi/sekretarica-zorica/venv/bin/python bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now zorica
```

**Useful commands:**

```bash
sudo systemctl status zorica
sudo journalctl -u zorica -f
sudo systemctl restart zorica
```

---

## Adding a new service

1. Create a new directory: `my_feature/`
2. Add `handler.py` with a `register(app, user_filter)` function
3. Add `service.py` with the core logic
4. Register it in `bot.py`:

```python
from my_feature import handler as my_feature
my_feature.register(app, user_filter)
```
