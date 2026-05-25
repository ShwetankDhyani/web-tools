# WebTools.wiki

Free, privacy-minded web utilities at [webtools.wiki](https://webtools.wiki).

## Tools

### Video Downloader
Download videos from YouTube, Vimeo, Twitter, Reddit, TikTok, and 1,000+ sites. Choose quality, then save the file. No account required.

### Paywall Remover
Read articles behind paywalls in a clean reader view. No account required.

### Price Tracker
Track product prices from Amazon, Flipkart, and other stores. Sign in with Telegram; get **Telegram messages** (via CallMeBot) when a price drops below your target. Choose check frequency (2–60 minutes). Uses stealth scraping with TLS fingerprint spoofing via curl_cffi.

**Admin:** set `ADMIN_USERNAME` or promote a user in the database (`is_admin = 1`).

## Quick Start

```bash
pip install -r requirements.txt
python app.py
```

Runs at `http://localhost:5000`.

## Production

Use **Gunicorn on port 8000** (nginx should `proxy_pass` to the same port).

```bash
gunicorn app:app --bind 127.0.0.1:8000 --workers 2 --threads 4
```

Systemd unit example: `deploy/webtools.service` (edit paths/user), then:

```bash
sudo cp deploy/webtools.service /etc/systemd/system/webtools.service
sudo systemctl daemon-reload
sudo systemctl enable --now webtools
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/
```

**502 Bad Gateway** usually means nginx and the app use different ports. Check:

```bash
sudo grep proxy_pass /etc/nginx/sites-enabled/*
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5000/
journalctl -u webtools -n 20 --no-pager
```

Cron (price checks):

```bash
*/3 * * * * cd /path/to/web-tools && python3 check_prices.py >> /var/log/price_checker.log 2>&1
```

## Docker

```bash
docker build -t webtools .
docker run -p 8000:8000 webtools
```

## Tech Stack

- **Backend:** Python / Flask
- **Video:** yt-dlp
- **Articles:** readability-lxml + BeautifulSoup
- **Frontend:** HTML / CSS / JS (no build step)
