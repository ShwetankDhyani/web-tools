# WebTools.wiki

Free, privacy-minded web utilities at [webtools.wiki](https://webtools.wiki).

**Source:** [github.com/ShwetankDhyani/web-tools](https://github.com/ShwetankDhyani/web-tools) (MIT)

## Tools

### Video Downloader
Download videos from YouTube, Vimeo, Twitter, Reddit, TikTok, and 1,000+ sites via yt-dlp. Choose quality, then save the file. No account required.

### Paywall Remover
Read articles in a clean reader view. HTML is sanitized server-side before display. No account required.

### Price Tracker
Track product prices from Amazon, Flipkart, and other stores. Sign in with Telegram; get **Telegram messages** (via CallMeBot) when a price drops below your target. Alerts re-arm after the price rises above target again. Choose check frequency (2–60 minutes).

**Admin:** set `ADMIN_USERNAME` to your Telegram username (recommended). Otherwise the first registrant becomes admin.

## Quick Start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export FLASK_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
python app.py
```

Runs at `http://localhost:5000`.

Ensure `yt-dlp` works (`yt-dlp --version` or `python -m yt_dlp --version`). FFmpeg is recommended for merges.

## Production

Use **Gunicorn on port 8000** (nginx should `proxy_pass` to the same port). Prefer **one worker** so video download progress is shared:

```bash
export FLASK_SECRET_KEY="…"
export FLASK_SESSION_SECURE=1
export ADMIN_USERNAME="your_telegram"
gunicorn app:app --bind 127.0.0.1:8000 --workers 1 --threads 8 --timeout 120
```

Systemd unit example: `deploy/webtools.service` (edit paths/user/secrets), then:

```bash
sudo cp deploy/webtools.service /etc/systemd/system/webtools.service
sudo systemctl daemon-reload
sudo systemctl enable --now webtools
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/
```

Nginx snippet with security headers: `deploy/nginx-snippet.conf`.

**502 Bad Gateway** usually means nginx and the app use different ports. Check:

```bash
sudo grep proxy_pass /etc/nginx/sites-enabled/*
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
journalctl -u webtools -n 20 --no-pager
```

Cron (price checks every 3 minutes):

```bash
*/3 * * * * cd /path/to/web-tools && ./venv/bin/python3 check_prices.py >> /var/log/price_checker.log 2>&1
```

## Docker

```bash
docker build -t webtools .
docker run -p 8000:8000 \
  -e FLASK_SECRET_KEY="$(openssl rand -hex 32)" \
  -e FLASK_SESSION_SECURE=1 \
  -e ADMIN_USERNAME=your_telegram \
  webtools
```

Note: price alerts still need a host cron (or sidecar) running `check_prices.py` against the same database volume.

## Security notes

- Set `FLASK_SECRET_KEY` (required for stable sessions).
- Set `ADMIN_USERNAME` to your Telegram username.
- Set `FLASK_SESSION_SECURE=1` behind HTTPS.
- Public fetch APIs block private/loopback hosts; OTP and download endpoints are rate-limited.
- Production video downloads need `yt-dlp` on `PATH` (or the Python package for `python -m yt_dlp`).
- Prefer `--workers 1` for the video downloader unless you add a shared task store (file-backed store is included and works across workers on a shared filesystem).

## Tech Stack

- **Backend:** Python / Flask / Gunicorn
- **Video:** yt-dlp (+ optional FFmpeg)
- **Articles:** readability-lxml + BeautifulSoup + bleach
- **Frontend:** HTML / CSS / JS (no build step)
