# WebTools.wiki — Oracle / VPS host (alongside other sites)

Chessreview.org is currently on **Vercel**. WebTools needs a long-running Python process,
SQLite, yt-dlp, ffmpeg, and cron — so it belongs on a VPS (Oracle Always Free works well).

This folder targets a fresh Ubuntu Oracle instance (or any Ubuntu VPS) with nginx + systemd.

## 1. DNS

Point these A records at your **Oracle public IP**:

| Name | Type | Value |
|------|------|--------|
| `@` (webtools.wiki) | A | ORACLE_IP |
| `www` | A | ORACLE_IP |

Keep TTL low (300s) during cutover. After SSL works, raise TTL again.

## 2. Server bootstrap (once, as a sudo-capable user)

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx python3-venv python3-full ffmpeg git

# App user (pick one that exists, or create)
sudo adduser --disabled-password --gecos '' webtools || true
sudo mkdir -p /home/webtools
sudo chown webtools:webtools /home/webtools
```

## 3. App install (as `webtools` or your SSH user)

```bash
cd ~
git clone https://github.com/ShwetankDhyani/web-tools.git
cd web-tools
git checkout devin/initial-push
python3 -m venv venv
source venv/bin/activate
pip install -U pip wheel
pip install -r requirements.txt
pip install -U yt-dlp

# Secrets
python3 - <<'PY'
import secrets
from pathlib import Path
p = Path('.env')
if not p.exists() or 'FLASK_SECRET_KEY=' not in p.read_text():
    p.write_text(f"FLASK_SECRET_KEY={secrets.token_hex(32)}\nFLASK_SESSION_SECURE=1\n")
    p.chmod(0o600)
print('env ok')
PY
```

## 4. Systemd (system service — preferred on Oracle)

Copy and edit paths/user in `deploy/webtools.oracle.service`, then:

```bash
sudo cp deploy/webtools.oracle.service /etc/systemd/system/webtools.service
sudo systemctl daemon-reload
sudo systemctl enable --now webtools
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5000/
```

## 5. Nginx site + TLS

```bash
sudo cp deploy/nginx-webtools.oracle.conf /etc/nginx/sites-available/webtools.wiki
# edit if app is not on 127.0.0.1:5000
sudo ln -sf /etc/nginx/sites-available/webtools.wiki /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d webtools.wiki -d www.webtools.wiki
```

## 6. Cron (price tracker)

```bash
crontab -e
# add:
*/3 * * * * cd /home/WEBUSER/web-tools && /home/WEBUSER/web-tools/venv/bin/python check_prices.py >> /home/WEBUSER/price_checker.log 2>&1
```

## 7. Cutover checklist

1. App responds on Oracle: `curl -I http://127.0.0.1:5000/`
2. Nginx + certbot green for webtools.wiki
3. Flip DNS A records to Oracle IP
4. Wait for propagation: `dig +short webtools.wiki`
5. Verify: `curl -I https://webtools.wiki/robots.txt` → 200
6. Stop Google instance later (optional) to save cost

## Optional: Docker

```bash
docker compose -f deploy/docker-compose.oracle.yml up -d --build
```

Still put nginx/Caddy in front for TLS, or terminate TLS on the host.
