#!/usr/bin/env bash
set -euo pipefail

DEVICE="${1:-${WEBOS_DEVICE:-}}"

if [ -z "$DEVICE" ]; then
  echo "Usage: $0 DEVICE_NAME" >&2
  echo "Example: $0 livingroom-tv" >&2
  exit 2
fi

ARES_LAUNCH_BIN="${ARES_LAUNCH_BIN:-}"
if [ -z "$ARES_LAUNCH_BIN" ]; then
  ARES_LAUNCH_BIN="$(command -v ares-launch || true)"
fi

if [ -z "$ARES_LAUNCH_BIN" ] || [ ! -x "$ARES_LAUNCH_BIN" ]; then
  echo "ares-launch was not found. Install @webos-tools/cli first." >&2
  exit 127
fi

echo "Renewing LG webOS Developer Mode session for device '$DEVICE'..."
"$ARES_LAUNCH_BIN" --device "$DEVICE" com.palmdts.devmode -p "extend=true"
echo "Developer Mode renewal request completed for '$DEVICE'."
