#!/bin/bash
# Start Tokenmeter at login. Removes with: ./install-login-item.sh --remove
set -e
LABEL="io.github.adi-debug-source.tokenmeter"
TARGET="gui/$(id -u)/$LABEL"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ "$1" = "--remove" ]; then
    launchctl bootout "$TARGET" 2>/dev/null || true
    rm -f "$PLIST"
    pkill -f "Tokenmeter.app/Contents/MacOS/Tokenmeter" 2>/dev/null || true
    echo "login item removed, app stopped"
    exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents"
sed "s|__HOME__|$HOME|g" "$(dirname "$0")/$LABEL.plist" > "$PLIST"
plutil -lint "$PLIST" >/dev/null
pkill -f "Tokenmeter.app/Contents/MacOS/Tokenmeter" 2>/dev/null || true
launchctl bootout "$TARGET" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Tokenmeter will now start at login"
