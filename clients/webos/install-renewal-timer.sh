#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
  echo "Run this installer as your normal user, not with sudo." >&2
  exit 1
fi

DEVICE="${1:-}"
if [ -z "$DEVICE" ]; then
  echo "Usage: $0 DEVICE_NAME" >&2
  echo "Example: $0 livingroom-tv" >&2
  exit 2
fi

for command_name in python3 ares-novacom ares-setup-device; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "$command_name was not found. Install @webos-tools/cli and Python 3 first." >&2
    exit 127
  fi
done

if ! ares-setup-device --list | awk -v device="$DEVICE" 'NR > 2 && $1 == device { found=1 } END { exit !found }'; then
  echo "webOS device '$DEVICE' is not registered for this user." >&2
  echo "Register it with ares-setup-device and retrieve its key with ares-novacom --getkey first." >&2
  exit 3
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="$(id -un)"
USER_HOME="${HOME:?HOME is not set}"
CONFIG_DIR="$USER_HOME/.config/uplinkwitness"
TOKEN_PATH="$CONFIG_DIR/webos-devmode-token"
INSTALL_DIR="/usr/local/lib/uplinkwitness"
SERVICE_NAME="uplinkwitness-webos-renew.service"
TIMER_NAME="uplinkwitness-webos-renew.timer"

mkdir -p "$CONFIG_DIR"
chmod 0700 "$CONFIG_DIR"

TMP_OUTPUT="$(mktemp)"
trap 'rm -f "$TMP_OUTPUT"' EXIT
chmod 0600 "$TMP_OUTPUT"

echo "Reading the Developer Mode session token from '$DEVICE' once..."
ares-novacom \
  --device "$DEVICE" \
  --run "cat /var/luna/preferences/devmode_enabled; echo" \
  >"$TMP_OUTPUT"

python3 - "$TMP_OUTPUT" "$TOKEN_PATH" <<'PY'
import os
import re
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])

raw = source.read_text(encoding="utf-8", errors="replace")
clean = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", raw)

tokens = []
for line in clean.splitlines():
    candidate = line.strip()
    if re.fullmatch(r"[0-9A-Fa-f]{64}", candidate):
        tokens.append(candidate)

tokens = list(dict.fromkeys(tokens))
if len(tokens) != 1:
    raise SystemExit(
        f"Expected exactly one Developer Mode token, found {len(tokens)}."
    )

target.write_text(tokens[0] + "\n", encoding="utf-8")
os.chmod(target, 0o600)
print("Developer Mode token stored privately with mode 600.")
PY

rm -f "$TMP_OUTPUT"
trap - EXIT

echo "Testing silent Developer Mode session check..."
"$SCRIPT_DIR/renew-devmode.sh"

sudo install -d -m 0755 "$INSTALL_DIR"
sudo install -m 0755 "$SCRIPT_DIR/renew-devmode.sh" "$INSTALL_DIR/renew-webos-devmode"

sudo tee "/etc/systemd/system/$SERVICE_NAME" >/dev/null <<EOF
[Unit]
Description=Renew LG webOS Developer Mode session for UplinkWitness
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=$USER_NAME
Environment="HOME=$USER_HOME"
ExecStart=$INSTALL_DIR/renew-webos-devmode
EOF

sudo tee "/etc/systemd/system/$TIMER_NAME" >/dev/null <<EOF
[Unit]
Description=Silent LG webOS Developer Mode renewal check for UplinkWitness

[Timer]
OnCalendar=Sun *-*-* 04:00:00
RandomizedDelaySec=30min
Persistent=true
Unit=$SERVICE_NAME

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now "$TIMER_NAME"

echo
echo "Installed $TIMER_NAME using silent server-side Developer Mode renewal."
echo "The TV is contacted only during this installation to read the session token."
echo "Scheduled checks contact LG's Developer Mode service, not the TV, and renew only below 14 days remaining."
echo "Check it with: systemctl list-timers $TIMER_NAME"
echo "Run it now with: sudo systemctl start $SERVICE_NAME"
echo "Inspect logs with: journalctl -u $SERVICE_NAME"
