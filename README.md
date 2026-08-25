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
| `PRICE_TRACKER_DEMO=1` | Show login codes on screen (local only). Production should omit this. |
| `ADMIN_USERNAME` | Telegram username treated as admin |
| `CRON_SECRET` | Bearer token for `POST /api/prices/check` |
| `FLASK_SESSION_SECURE=1` | Mark session cookie Secure (HTTPS) |

Price Tracker sends OTP and drop alerts through [CallMeBot](https://www.callmebot.com/) (no API key). Users must send `/start` to [@CallMeBot_txtbot](https://t.me/CallMeBot_txtbot) once.

Cron on the VPS (every 5 minutes):

```bash
*/5 * * * * curl -sS -X POST http://127.0.0.1:4321/api/prices/check >/dev/null
```

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
