#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="${HORO_SERVICE_USER:-$(id -un)}"
SERVICE_GROUP="$(id -gn "$SERVICE_USER")"
DATA_DIR="/var/lib/horo-memory"
ENV_FILE="/etc/horo-memory.env"
UNIT_FILE="/etc/systemd/system/horo-memory.service"

python3 -m venv "$ROOT_DIR/.venv"
"$ROOT_DIR/.venv/bin/python" -m pip install --upgrade pip
"$ROOT_DIR/.venv/bin/pip" install "$ROOT_DIR[graphify]"

sudo install -d -o "$SERVICE_USER" -g "$SERVICE_GROUP" -m 0750 "$DATA_DIR"

if ! sudo test -f "$ENV_FILE"; then
  token="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  temporary="$(mktemp)"
  chmod 0600 "$temporary"
  cat >"$temporary" <<EOF
HORO_API_TOKEN=$token
HORO_DATA_DIR=$DATA_DIR
HORO_HOST=127.0.0.1
HORO_PORT=8088
HORO_GRAPHIFY_ENABLED=true
HORO_GRAPHIFY_COMMAND=graphify
EOF
  sudo install -o root -g "$SERVICE_GROUP" -m 0640 "$temporary" "$ENV_FILE"
  rm -f "$temporary"
fi

temporary_unit="$(mktemp)"
sed \
  -e "s|__HORO_USER__|$SERVICE_USER|g" \
  -e "s|__HORO_GROUP__|$SERVICE_GROUP|g" \
  -e "s|__HORO_ROOT__|$ROOT_DIR|g" \
  "$ROOT_DIR/deploy/horo-memory.service.in" >"$temporary_unit"
sudo install -o root -g root -m 0644 "$temporary_unit" "$UNIT_FILE"
rm -f "$temporary_unit"

sudo systemctl daemon-reload
sudo systemctl enable --now horo-memory.service
sudo systemctl --no-pager --full status horo-memory.service
