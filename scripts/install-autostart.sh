#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$AGENTS_DIR" "$ROOT/.data"

render_plist() {
  local label="$1"
  local script="$2"
  local keep_alive="$3"

  cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${script}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <${keep_alive}/>
  <key>StandardOutPath</key>
  <string>${ROOT}/.data/${label}.log</string>
  <key>StandardErrorPath</key>
  <string>${ROOT}/.data/${label}.log</string>
</dict>
</plist>
EOF
}

RELAY_PLIST="$AGENTS_DIR/com.gia9.imessage-relay.plist"
BOT_PLIST="$AGENTS_DIR/com.gia9.monitor.plist"

render_plist "com.gia9.imessage-relay" "$ROOT/scripts/run-imessage-relay.sh" "true" > "$RELAY_PLIST"
render_plist "com.gia9.monitor" "$ROOT/scripts/docker-up.sh" "false" > "$BOT_PLIST"

launchctl bootout "gui/$(id -u)/com.gia9.imessage-relay" 2>/dev/null || true
launchctl bootout "gui/$(id -u)/com.gia9.monitor" 2>/dev/null || true

launchctl bootstrap "gui/$(id -u)" "$RELAY_PLIST"
launchctl bootstrap "gui/$(id -u)" "$BOT_PLIST"

launchctl enable "gui/$(id -u)/com.gia9.imessage-relay"
launchctl enable "gui/$(id -u)/com.gia9.monitor"
launchctl kickstart -k "gui/$(id -u)/com.gia9.imessage-relay"
launchctl kickstart -k "gui/$(id -u)/com.gia9.monitor"

echo "Автозапуск установлен:"
echo "  $RELAY_PLIST"
echo "  $BOT_PLIST"
