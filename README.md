# WebTools

A collection of free, privacy-first web utilities.

## Tools

### Video Downloader
Download videos from YouTube, Vimeo, Twitter, Reddit, TikTok, and 1000+ sites. Choose your preferred quality and format.

### Paywall Remover
Read articles behind paywalls. Fetches the original content and presents it in a clean, distraction-free reader view.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the development server
python app.py
```

The app runs on `http://localhost:5000`.

## Production

```bash
gunicorn app:app --bind 0.0.0.0:8000 --workers 4 --threads 4
```

## Docker

```bash
docker build -t webtools .
docker run -p 8000:8000 webtools
```

## Tech Stack

- **Backend:** Python / Flask
- **Video Downloads:** yt-dlp
- **Article Extraction:** readability-lxml + BeautifulSoup
- **Frontend:** Vanilla HTML / CSS / JS (no build step)
