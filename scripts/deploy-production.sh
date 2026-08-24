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

# Prefer 3.12/3.13 when present — brand-new CPython sometimes lacks wheels.
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in python3.12 python3.13 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done
fi
echo "==> Using Python: $PYTHON_BIN ($("$PYTHON_BIN" -V 2>&1))"

# Recreate venv if missing or built for a different interpreter major.minor
NEED_VENV=0
if [[ ! -x venv/bin/python ]]; then
  NEED_VENV=1
else
  CUR="$("$APP_DIR/venv/bin/python" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
  WANT="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
  if [[ "$CUR" != "$WANT" ]]; then
    echo "==> Recreating venv ($CUR -> $WANT)"
    NEED_VENV=1
  fi
fi
if [[ "$NEED_VENV" -eq 1 ]]; then
  rm -rf venv
  "$PYTHON_BIN" -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate
PIP="$APP_DIR/venv/bin/pip"
PY="$APP_DIR/venv/bin/python"
GUNICORN="$APP_DIR/venv/bin/gunicorn"

echo "==> Installing dependencies into venv"
"$PIP" install --upgrade pip wheel
# Prefer binary wheels so lxml never compiles from source on the VPS
if ! "$PIP" install --only-binary=:all: -r requirements.txt; then
  echo "==> Binary-only install failed; retrying with source builds allowed"
  "$PIP" install -r requirements.txt
fi
"$PIP" install -U "yt-dlp==2025.4.30" || "$PIP" install -U yt-dlp

# Ensure yt-dlp is callable on PATH for the service user
mkdir -p "$HOME/.local/bin"
ln -sfn "$APP_DIR/venv/bin/yt-dlp" "$HOME/.local/bin/yt-dlp"
export PATH="$HOME/.local/bin:$APP_DIR/venv/bin:$PATH"

# Ensure FLASK_SECRET_KEY persists across restarts
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
if [[ ! -f "$ENV_FILE" ]] || ! grep -q '^FLASK_SECRET_KEY=' "$ENV_FILE" 2>/dev/null; then
  KEY="$("$PY" -c 'import secrets; print(secrets.token_hex(32))')"
  umask 077
  {
    echo "FLASK_SECRET_KEY=$KEY"
    echo "FLASK_SESSION_SECURE=1"
  } >> "$ENV_FILE"
  echo "==> Wrote new FLASK_SECRET_KEY to $ENV_FILE"
fi
grep -q '^FLASK_SESSION_SECURE=' "$ENV_FILE" 2>/dev/null || echo "FLASK_SESSION_SECURE=1" >> "$ENV_FILE"

if command -v systemctl >/dev/null 2>&1; then
  echo "==> Updating systemd unit for $SERVICE"
  if [[ -f deploy/webtools.service ]]; then
    sudo cp deploy/webtools.service "/etc/systemd/system/${SERVICE}.service" || true
  fi
  sudo mkdir -p "/etc/systemd/system/${SERVICE}.service.d"
  sudo tee "/etc/systemd/system/${SERVICE}.service.d/override.conf" >/dev/null <<OV
[Service]
EnvironmentFile=-${ENV_FILE}
Environment=PATH=${APP_DIR}/venv/bin:/usr/local/bin:/usr/bin
ExecStart=
ExecStart=${GUNICORN} app:app --bind 127.0.0.1:8000 --workers 1 --threads 8 --timeout 120
OV
  sudo systemctl daemon-reload
  echo "==> Restarting $SERVICE"
  sudo systemctl restart "$SERVICE"
  sleep 2
  sudo systemctl --no-pager --full status "$SERVICE" | head -25 || true
fi

echo "==> Smoke checks"
curl -s -o /dev/null -w "home %{http_code}\n" http://127.0.0.1:8000/ || true
curl -s -o /dev/null -w "robots %{http_code}\n" http://127.0.0.1:8000/robots.txt || true
curl -s -o /dev/null -w "privacy %{http_code}\n" http://127.0.0.1:8000/privacy || true
curl -s -o /dev/null -w "public %{http_code}\n" https://webtools.wiki/ || true
echo -n "video "
curl -s -X POST https://webtools.wiki/api/video/info \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=jNQXAC9IVRw"}' | head -c 220 || true
echo
echo "Deploy complete."
