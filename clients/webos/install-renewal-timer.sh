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

if ! command -v ares-launch >/dev/null 2>&1; then
  echo "ares-launch was not found. Install @webos-tools/cli first." >&2
  exit 127
fi

if ! command -v ares-setup-device >/dev/null 2>&1; then
  echo "ares-setup-device was not found. Install @webos-tools/cli first." >&2
  exit 127
fi

if ! ares-setup-device --list | awk -v device="$DEVICE" 'NR > 2 && $1 == device { found=1 } END { exit !found }'; then
  echo "webOS device '$DEVICE' is not registered for this user." >&2
  echo "Register it with ares-setup-device and retrieve its key with ares-novacom --getkey first." >&2
  exit 3
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="$(id -un)"
USER_HOME="${HOME:?HOME is not set}"
ARES_LAUNCH_BIN="$(command -v ares-launch)"
INSTALL_DIR="/usr/local/lib/uplinkwitness"
SERVICE_NAME="uplinkwitness-webos-renew.service"
TIMER_NAME="uplinkwitness-webos-renew.timer"

echo "Testing Developer Mode renewal before installing the timer..."
ARES_LAUNCH_BIN="$ARES_LAUNCH_BIN" "$SCRIPT_DIR/renew-devmode.sh" "$DEVICE"

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
Environment="ARES_LAUNCH_BIN=$ARES_LAUNCH_BIN"
ExecStart=$INSTALL_DIR/renew-webos-devmode $DEVICE
EOF

sudo tee "/etc/systemd/system/$TIMER_NAME" >/dev/null <<EOF
[Unit]
Description=Weekly LG webOS Developer Mode renewal for UplinkWitness

[Timer]
OnBootSec=15min
OnUnitActiveSec=7d
RandomizedDelaySec=30min
Persistent=true
Unit=$SERVICE_NAME

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now "$TIMER_NAME"

echo
echo "Installed $TIMER_NAME for webOS device '$DEVICE'."
echo "The session will be renewed about once a week, with a renewal attempt after host boots."
echo "Check it with: systemctl list-timers $TIMER_NAME"
echo "Run it now with: sudo systemctl start $SERVICE_NAME"
echo "Inspect logs with: journalctl -u $SERVICE_NAME"
