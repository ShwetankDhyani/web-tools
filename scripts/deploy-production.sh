#!/usr/bin/env bash
# Run on the webtools.wiki VPS as the app user (setu_dhyani).
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/web-tools}"
BRANCH="${BRANCH:-devin/initial-push}"
SERVICE="${SERVICE:-webtools}"

cd "$APP_DIR"

echo "==> Fetching $BRANCH"
git fetch origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

if [[ -d venv ]]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

echo "==> Installing dependencies"
python3 -m pip install -r requirements.txt
python3 -m pip install -U "yt-dlp==2025.4.30" || python3 -m pip install -U yt-dlp

# Ensure FLASK_SECRET_KEY persists across restarts
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
if [[ ! -f "$ENV_FILE" ]] || ! grep -q '^FLASK_SECRET_KEY=' "$ENV_FILE" 2>/dev/null; then
  KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  {
    echo "FLASK_SECRET_KEY=$KEY"
    echo "FLASK_SESSION_SECURE=1"
  } >> "$ENV_FILE"
  echo "==> Wrote new FLASK_SECRET_KEY to $ENV_FILE"
fi

# Load env into systemd drop-in if possible
if command -v systemctl >/dev/null 2>&1; then
  echo "==> Restarting $SERVICE"
  # Prefer updated unit if present
  if [[ -f deploy/webtools.service ]]; then
    sudo cp deploy/webtools.service "/etc/systemd/system/${SERVICE}.service" || true
    # Inject EnvironmentFile
    sudo mkdir -p "/etc/systemd/system/${SERVICE}.service.d"
    sudo tee "/etc/systemd/system/${SERVICE}.service.d/override.conf" >/dev/null <<OV
[Service]
EnvironmentFile=-${ENV_FILE}
ExecStart=
ExecStart=$(command -v gunicorn || echo "$APP_DIR/venv/bin/gunicorn") app:app --bind 127.0.0.1:8000 --workers 1 --threads 8 --timeout 120
OV
    sudo systemctl daemon-reload
  fi
  sudo systemctl restart "$SERVICE"
  sleep 2
  sudo systemctl --no-pager --full status "$SERVICE" | head -20 || true
fi

echo "==> Smoke checks"
curl -s -o /dev/null -w "home %{http_code}\n" http://127.0.0.1:8000/
curl -s -o /dev/null -w "robots %{http_code}\n" http://127.0.0.1:8000/robots.txt
curl -s -o /dev/null -w "privacy %{http_code}\n" http://127.0.0.1:8000/privacy/
# via public host if nginx up
curl -s -o /dev/null -w "public %{http_code}\n" https://webtools.wiki/ || true
curl -s -X POST https://webtools.wiki/api/video/info \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=jNQXAC9IVRw"}' | head -c 200 || true
echo
echo "Deploy complete."
