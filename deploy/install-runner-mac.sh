#!/usr/bin/env bash
# Run the local runner automatically on this Mac: starts at login, restarts
# after a crash, and keeps the Mac from idle-sleeping while running.
#
#   PROJECT_ID=my-project ./deploy/install-runner-mac.sh            # install or update
#   ./deploy/install-runner-mac.sh uninstall                        # remove
#
# Logs: ~/Library/Logs/aicc-runner.log
set -euo pipefail

LABEL="edu.usf.aicc.runner"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG="$HOME/Library/Logs/aicc-runner.log"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOMAIN="gui/$(id -u)"

if launchctl print "${DOMAIN}/${LABEL}" >/dev/null 2>&1; then
  launchctl bootout "${DOMAIN}/${LABEL}" || true
fi
if [ "${1:-}" = "uninstall" ]; then
  rm -f "$PLIST"
  echo "Runner removed. Courses already queued stay queued."
  exit 0
fi

: "${PROJECT_ID:?set PROJECT_ID, e.g. PROJECT_ID=my-project}"
for tool in gcloud ffmpeg tesseract deno; do
  command -v "$tool" >/dev/null || { echo "Missing $tool; install it first." >&2; exit 1; }
done
[ -x "$ROOT/.venv/bin/python" ] || { echo "No .venv in $ROOT" >&2; exit 1; }
GCLOUD_BIN="$(dirname "$(command -v gcloud)")"

mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG")"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string><string>-i</string>
    <string>${ROOT}/.venv/bin/python</string><string>-u</string>
    <string>${ROOT}/runner.py</string>
    <string>--project</string><string>${PROJECT_ID}</string>
  </array>
  <key>WorkingDirectory</key><string>${ROOT}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>${ROOT}/.venv/bin:${GCLOUD_BIN}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>StandardOutPath</key><string>${LOG}</string>
  <key>StandardErrorPath</key><string>${LOG}</string>
</dict>
</plist>
PLIST
launchctl bootstrap "$DOMAIN" "$PLIST"
echo "Runner installed and started. Logs: $LOG"
