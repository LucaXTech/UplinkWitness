#!/usr/bin/env bash
set -euo pipefail

TOKEN_PATH="${WEBOS_DEVMODE_TOKEN_PATH:-${HOME:?HOME is not set}/.config/uplinkwitness/webos-devmode-token}"
RENEW_THRESHOLD_HOURS="${WEBOS_RENEW_THRESHOLD_HOURS:-336}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found." >&2
  exit 127
fi

python3 - "$TOKEN_PATH" "$RENEW_THRESHOLD_HOURS" <<'PY'
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

TOKEN_PATH = Path(sys.argv[1])
RENEW_THRESHOLD_HOURS = int(sys.argv[2])
BASE_URL = "https://developer.lge.com/secure/"


def api_call(endpoint, token):
    url = BASE_URL + endpoint + "?" + urllib.parse.urlencode({
        "sessionToken": token
    })
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "UplinkWitness/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read())


def require_success(result, operation):
    if (
        result.get("result") != "success"
        or str(result.get("errorCode")) != "200"
    ):
        raise RuntimeError(
            f"{operation} failed: "
            f"{result.get('errorCode')} {result.get('errorMsg')}"
        )


def parse_remaining(value):
    parts = str(value).split(":")
    if len(parts) != 3:
        raise ValueError(f"Unexpected remaining time: {value!r}")
    hours, minutes, seconds = map(int, parts)
    return hours * 3600 + minutes * 60 + seconds


if not TOKEN_PATH.exists():
    raise SystemExit(f"Developer Mode token missing: {TOKEN_PATH}")

token = TOKEN_PATH.read_text(encoding="utf-8").strip()
if not re.fullmatch(r"[0-9A-Fa-f]{64}", token):
    raise SystemExit("Developer Mode token has unexpected format")

status = api_call("CheckDevModeSession.dev", token)
require_success(status, "CheckDevModeSession")

remaining_text = status.get("errorMsg", "")
remaining_seconds = parse_remaining(remaining_text)
threshold_seconds = RENEW_THRESHOLD_HOURS * 3600

print(f"Developer Mode remaining: {remaining_text}")

if remaining_seconds > threshold_seconds:
    print("Renewal not required.")
    raise SystemExit(0)

print("Renewing Developer Mode session silently via LG server...")
renewal = api_call("ResetDevModeSession.dev", token)
require_success(renewal, "ResetDevModeSession")

status = api_call("CheckDevModeSession.dev", token)
require_success(status, "CheckDevModeSession after renewal")
print(
    "Developer Mode renewed successfully. "
    f"Remaining: {status.get('errorMsg')}"
)
PY
