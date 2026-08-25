# WebTools.wiki — migrate fully to Oracle / Ubuntu VPS

Yes. This Next.js stack is designed for a VPS: long-running Node, yt-dlp, FFmpeg, and on-disk download/price data. Vercel is fine for UI previews; production belongs on your Oracle box.

Your domain already points here (`webtools.wiki` → Oracle). Nginx is up; the old Flask process is down (502). Cut over by replacing that process with Next.js.

## Requirements on the VPS

- Ubuntu (Oracle Always Free is fine)
- Node.js 20+
- nginx + certbot (you likely already have these)
- ffmpeg
- yt-dlp (`pip install --user yt-dlp` or system package)
- ~1–2 GB free disk for temp downloads

## One-shot cutover (as `ubuntu` on the VPS)

```bash
# 0) Stop the dead Flask service if it exists
sudo systemctl stop webtools 2>/dev/null || true
sudo systemctl disable webtools 2>/dev/null || true

# 1) System packages
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx ffmpeg git curl python3-pip

# Node 22 (NodeSource) — skip if node -v already shows 20+
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs

# yt-dlp
python3 -m pip install --user -U yt-dlp
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
export PATH="$HOME/.local/bin:$PATH"
yt-dlp --version
ffmpeg -version | head -1

# 2) App
cd ~
# Fresh clone of the flagship branch (or pull if you already have web-tools)
if [ -d web-tools/.git ]; then
  cd web-tools
  git fetch origin
  git checkout flagship/nextjs
  git pull origin flagship/nextjs
else
  git clone -b flagship/nextjs https://github.com/ShwetankDhyani/web-tools.git
  cd web-tools
fi

npm ci
npm run build

# 3) Secrets
cat > .env <<EOF
FLASK_SESSION_SECURE=1
EOF
chmod 600 .env

mkdir -p data/prices data/downloads

# 4) systemd
sudo cp deploy/webtools.next.oracle.service /etc/systemd/system/webtools.service
# Edit User/paths in that file if your home is not /home/ubuntu
sudo systemctl daemon-reload
sudo systemctl enable --now webtools
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:4321/

# 5) nginx → Next (port 4321)
sudo cp deploy/nginx-webtools.next.oracle.conf /etc/nginx/sites-available/webtools.wiki
sudo ln -sf /etc/nginx/sites-available/webtools.wiki /etc/nginx/sites-enabled/webtools.wiki
# Remove any old site that still proxies to Flask :5000
sudo nginx -t && sudo systemctl reload nginx

# TLS (skip if certs already exist)
sudo certbot --nginx -d webtools.wiki -d www.webtools.wiki --non-interactive --agree-tos -m you@example.com || true

curl -sI https://webtools.wiki | head -5
```

## What changes vs the old Flask deploy

| Old | New |
| --- | --- |
| Gunicorn `:5000` | `next start` `:4321` |
| Python venv + `requirements.txt` | `npm ci` + `npm run build` |
| `static/` served by nginx | Next serves assets; nginx only proxies |
| SQLite `price_tracker.db` | JSON store under `data/prices/` |

## Updates later

```bash
cd ~/web-tools
git pull origin flagship/nextjs
npm ci
npm run build
sudo systemctl restart webtools
```

Or: `bash scripts/deploy-oracle.sh` (after the first install).

## Optional: Docker on Oracle

```bash
cd ~/web-tools
docker build -t webtools .
docker run -d --name webtools --restart unless-stopped \
  -p 127.0.0.1:4321:4321 \
  -v "$(pwd)/data:/app/data" \
  -e FLASK_SESSION_SECURE=1 \
  webtools
```

Point nginx at `127.0.0.1:4321` the same way.

## Checklist after cutover

1. `https://webtools.wiki` returns 200 (not 502)
2. `/video` fetches a non-YouTube URL (Archive.org works; YouTube may need cookies on the server)
3. `/reader` loads a Wikipedia article
4. `/prices` demo or CallMeBot login works
5. `journalctl -u webtools -n 50 --no-pager` is clean

## If you still see 502

```bash
sudo systemctl status webtools --no-pager
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:4321/
sudo grep -R proxy_pass /etc/nginx/sites-enabled/
journalctl -u webtools -n 40 --no-pager
```

Almost always: nginx still proxies to `:5000`, or the Node service isn’t running.
