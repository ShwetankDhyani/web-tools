# WebTools.wiki

Free everyday utilities with flagship craft — [webtools.wiki](https://webtools.wiki).

This repository is a full redesign of [ShwetankDhyani/web-tools](https://github.com/ShwetankDhyani/web-tools): same jobs to be done, rebuilt as a modern Next.js product a serious engineering org would ship.

## Tools

| Tool | What it does |
| --- | --- |
| **Video Downloader** | Fetch metadata and download from 1,000+ sites via yt-dlp. No account. |
| **Reader** | Distraction-free article view from a public URL (Mozilla Readability). No account. |
| **Price Tracker** | Track store prices; sign in with Telegram username; demo OTP locally. |

## Quick start

```bash
# Node 20+
npm install

# yt-dlp on PATH (Video Downloader)
python3 -m pip install --user yt-dlp
export PATH="$HOME/.local/bin:$PATH"

npm run dev
```

Open [http://127.0.0.1:4321](http://127.0.0.1:4321).

### Production

```bash
npm run build
npm start
```

### Oracle / Ubuntu VPS (recommended for webtools.wiki)

Full cutover from the old Flask service: see **[deploy/ORACLE.md](deploy/ORACLE.md)**.  
Unit file: `deploy/webtools.next.oracle.service` · nginx: `deploy/nginx-webtools.next.oracle.conf` · updates: `scripts/deploy-oracle.sh`.

### Optional environment

| Variable | Purpose |
| --- | --- |
| `CALLMEBOT_APIKEY` | Deliver Price Tracker OTP / alerts via CallMeBot |
| `ADMIN_USERNAME` | Telegram username treated as admin |
| `PRICE_TRACKER_DEMO=0` | Disable returning OTP codes in API responses |
| `FLASK_SESSION_SECURE=1` | Mark session cookie Secure (HTTPS) |

Without `CALLMEBOT_APIKEY`, Price Tracker runs in **demo mode** and shows the login code on screen.

## Stack

- Next.js (App Router) · TypeScript · Tailwind CSS · shadcn/ui
- yt-dlp (+ FFmpeg recommended for merges)
- `@mozilla/readability` + `linkedom` + `sanitize-html`
- File-backed download task store and price tracker store under `data/`

## Design notes

- Brand-first landing with Syne + Source Sans 3 + Literata (reader)
- “Precision daylight” palette — cool mist, ink type, teal signal (no purple glow theme)
- SSRF checks and rate limits on public fetch APIs
- Reader is positioned as a reading mode for publicly available HTML — not a paywall circumvention product

## License

MIT
