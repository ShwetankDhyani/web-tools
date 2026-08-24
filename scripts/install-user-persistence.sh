#!/usr/bin/env bash
# Install a persistent starter that does NOT need root/sudo.
# Prefers systemd --user; falls back to crontab @reboot.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/web-tools}"
BIND_ADDR="${BIND_ADDR:-127.0.0.1:5000}"
UNIT_SRC="$APP_DIR/deploy/webtools.user.service"
UNIT_DST="$HOME/.config/systemd/user/webtools.service"

cd "$APP_DIR"

start_foreground_check() {
  curl -sf -o /dev/null "http://${BIND_ADDR}/robots.txt"
}

ensure_running_now() {
  if start_foreground_check; then
    echo "==> Already responding on ${BIND_ADDR}"
    return 0
  fi
  echo "==> Starting gunicorn now on ${BIND_ADDR}"
  set -a
  # shellcheck disable=SC1091
  [[ -f "$APP_DIR/.env" ]] && . "$APP_DIR/.env"
  set +a
  nohup "$APP_DIR/venv/bin/gunicorn" app:app \
    --bind "$BIND_ADDR" --workers 1 --threads 8 --timeout 120 \
    >>"$APP_DIR/gunicorn.log" 2>&1 &
  sleep 2
  start_foreground_check && echo "==> Up"
}

if systemctl --user status >/dev/null 2>&1; then
  echo "==> Installing systemd user unit"
  mkdir -p "$HOME/.config/systemd/user"
  cp "$UNIT_SRC" "$UNIT_DST"
  # Stop any stray manual gunicorn so the unit owns the port
  pkill -u "$(id -u)" -f 'gunicorn.*app:app' 2>/dev/null || true
  sleep 1
  systemctl --user daemon-reload
  systemctl --user enable --now webtools.service
  sleep 2
  systemctl --user --no-pager --full status webtools.service | head -20 || true
  if start_foreground_check; then
    echo "==> User systemd service is active"
    echo "Note: without lingering, this stops at logout. Enable linger if you can:"
    echo "  loginctl enable-linger $(whoami)   # may require root"
    echo "Or keep the crontab fallback below as belt-and-suspenders."
  fi
else
  echo "==> systemd --user unavailable; will use crontab"
  ensure_running_now
fi

# Always ensure a reboot cron exists (works without sudo / linger)
START_CMD="cd $APP_DIR && set -a && . .env && set +a && export PATH=$APP_DIR/venv/bin:\$PATH && exec $APP_DIR/venv/bin/gunicorn app:app --bind $BIND_ADDR --workers 1 --threads 8 --timeout 120 >>$APP_DIR/gunicorn.log 2>&1"
CRON_LINE="@reboot sleep 15 && $START_CMD"
EXISTING="$(crontab -l 2>/dev/null || true)"
if echo "$EXISTING" | grep -qF 'web-tools/venv/bin/gunicorn'; then
  echo "==> crontab @reboot already present"
else
  printf '%s\n%s\n' "$EXISTING" "$CRON_LINE" | sed '/^$/d' | crontab -
  echo "==> Installed crontab @reboot starter"
fi

crontab -l | grep -F 'web-tools' || true
ensure_running_now
curl -s -o /dev/null -w "local robots %{http_code}\n" "http://${BIND_ADDR}/robots.txt" || true
curl -s -o /dev/null -w "public robots %{http_code}\n" https://webtools.wiki/robots.txt || true
echo "Done. No sudo required."
