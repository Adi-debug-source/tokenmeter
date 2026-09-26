#!/bin/bash
# Build Tokenmeter.app and install it into ~/Applications.
# Needs the Xcode command line tools (xcode-select --install).
set -e
cd "$(dirname "$0")"
APP="$HOME/Applications/Tokenmeter.app"
LABEL="io.github.adi-debug-source.tokenmeter"
MANAGED=0
launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1 && MANAGED=1

swiftc -O -o costbar main.swift -framework AppKit

# The icon is drawn by icon.swift rather than stored as a binary. Rebuilt only
# when the source is newer, because compiling it costs a few seconds and it
# changes far less often than the app does.
if [ ! -f AppIcon.icns ] || [ icon.swift -nt AppIcon.icns ]; then
    echo "drawing the icon"
    swiftc -O -o .mkicon icon.swift -framework AppKit
    # iconutil requires a name before the .iconset extension; a bare
    # ".iconset" is rejected as an invalid iconset.
    rm -rf AppIcon.iconset && ./.mkicon AppIcon.iconset >/dev/null
    iconutil -c icns AppIcon.iconset -o AppIcon.icns
    rm -rf AppIcon.iconset .mkicon
fi

# Stop it before touching the bundle. Replacing a running app's binary is what
# invalidates the signature and gets it killed with OS_REASON_CODESIGNING.
[ "$MANAGED" = 1 ] && launchctl kill SIGTERM "gui/$(id -u)/$LABEL" 2>/dev/null || true
pkill -f "Tokenmeter.app/Contents/MacOS/Tokenmeter" 2>/dev/null || true
sleep 1

# Build the bundle beside the target, then swap it in, so the live bundle is
# never half written.
STAGE="$(mktemp -d)/Tokenmeter.app"
mkdir -p "$STAGE/Contents/MacOS"
cp costbar "$STAGE/Contents/MacOS/Tokenmeter"
cp Info.plist "$STAGE/Contents/Info.plist"
mkdir -p "$STAGE/Contents/Resources"
cp AppIcon.icns "$STAGE/Contents/Resources/AppIcon.icns"
xattr -cr "$STAGE"
# Ad-hoc signed, which is all a locally built app needs. No --deep: it is
# deprecated and produces signatures the loader rejects here.
codesign --force --sign - "$STAGE"
codesign --verify --strict "$STAGE"

rm -rf "$APP"
mkdir -p "$HOME/Applications"
mv "$STAGE" "$APP"
rmdir "$(dirname "$STAGE")" 2>/dev/null || true

if [ "$MANAGED" = 1 ]; then
    # A full bootout/bootstrap, not kickstart. launchd caches the code
    # signature it registered for this path, and an ad-hoc signature changes
    # on every build, so kickstart relaunches the new binary against the old
    # signature and the kernel kills it with OS_REASON_CODESIGNING.
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    sleep 1
    launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/$LABEL.plist"
    echo "rebuilt and reloaded via launchd: $APP"
else
    open "$APP"
    echo "rebuilt and running: $APP"
    echo "to start it at login:  ./install-login-item.sh"
fi
