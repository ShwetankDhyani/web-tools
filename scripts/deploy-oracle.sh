#!/usr/bin/env bash
# Update WebTools.wiki on an already-bootstrapped Oracle VPS.
set -euo pipefail

ROOT="${WEBTOOLS_ROOT:-$HOME/web-tools}"
BRANCH="${WEBTOOLS_BRANCH:-flagship/nextjs}"

cd "$ROOT"
export PATH="$HOME/.local/bin:$PATH"

git fetch origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

npm ci
npm run build
mkdir -p data/prices data/downloads

sudo systemctl restart webtools
sleep 1
code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:4321/ || true)
echo "local health: $code"
systemctl is-active webtools
