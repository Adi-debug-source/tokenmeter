#!/bin/bash
# Install Tokenmeter from this folder. Safe to run again after pulling changes.
#
#   ./install.sh               install or update
#   ./install.sh --statusline  also replace an existing Claude Code status line
#   ./install.sh --no-app      skip the menu bar app
#   ./install.sh --uninstall   remove it (your usage ledger is kept)
#
# Needs python3 3.9 or later (macOS ships it with the command line tools), and
# the Xcode command line tools for the menu bar app: xcode-select --install
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
TARGET="$HOME/.claude/tools/tokenmeter"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$CLAUDE_DIR/settings.json"
LABEL="io.github.adi-debug-source.tokenmeter"
APP="$HOME/Applications/Tokenmeter.app"
say() { printf '  %s\n' "$1"; }

to_bin() {  # move, never delete, so anything removed can be put back. $2 = what to say
    [ -e "$1" ] || return 0
    local name; name="$(basename "$1")"
    local dest="$HOME/.Trash/$name"
    [ -e "$dest" ] && dest="$HOME/.Trash/$name $(date +%H%M%S)"
    mkdir -p "$HOME/.Trash"
    mv "$1" "$dest"
    [ -n "$2" ] && say "$2"
    return 0
}

STATUSLINE=set
APP_WANTED=1
UNINSTALL=0
for arg in "$@"; do
    case "$arg" in
        --statusline) STATUSLINE=set-force ;;
        --no-app) APP_WANTED=0 ;;
        --uninstall) UNINSTALL=1 ;;
        *) echo "unknown option $arg"; exit 2 ;;
    esac
done

statusline_edit() {  # $1 = set | set-force | remove
    python3 - "$SETTINGS" "$1" "python3 $TARGET/statusline.py" <<'PY'
import json, os, sys
path, mode, command = sys.argv[1:4]
try:
    with open(path) as f:
        cfg = json.load(f)
except FileNotFoundError:
    cfg = {}
except ValueError:
    print("  settings.json is not valid JSON, so it was left alone")
    sys.exit(0)
ours = {"type": "command", "command": command, "padding": 0}
current = cfg.get("statusLine")
mine = isinstance(current, dict) and "tokenmeter" in str(current.get("command", ""))
if mode == "remove":
    if mine:
        del cfg["statusLine"]
        print("  status line removed from settings.json")
    else:
        sys.exit(0)
elif current == ours:
    print("  status line already set up")
    sys.exit(0)
elif current and not mine and mode != "set-force":
    print("  you already have a status line, so it was left alone.")
    print("  to use Tokenmeter's instead:  ./install.sh --statusline")
    sys.exit(0)
else:
    cfg["statusLine"] = ours
    print("  status line added to settings.json")
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
PY
}

echo
echo "Tokenmeter"
echo "----------"

if [ "$UNINSTALL" = 1 ]; then
    if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
        "$SRC/costbar/install-login-item.sh" --remove >/dev/null 2>&1 || true
        say "login item removed"
    fi
    to_bin "$APP" "menu bar app moved to the Bin"
    [ -f "$SETTINGS" ] && statusline_edit remove
    to_bin "$CLAUDE_DIR/commands/tokenmeter.md" "/tokenmeter command moved to the Bin"
    to_bin "$TARGET" "engine moved to the Bin"
    say "your usage ledger was kept: ${TOKENMETER_LEDGER:-$HOME/.claude/cost-ledger.jsonl}"
    echo
    exit 0
fi

# 1. Python
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    echo "  python3 3.9 or later is needed. Install the command line tools:"
    echo "    xcode-select --install"
    exit 1
fi

# 2. The engine, copied from this folder into its home. Code folders are
#    replaced whole so a renamed file cannot linger; the caches beside the
#    engine (exchange rates, looked-up prices) are kept.
mkdir -p "$TARGET"
for d in adapters pricing fonts; do
    rm -rf "${TARGET:?}/$d"
    cp -R "$SRC/$d" "$TARGET/$d"
done
find "$TARGET" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
cp "$SRC/tokenmeter.py" "$SRC/statusline.py" "$TARGET/"
chmod +x "$TARGET/tokenmeter.py" "$TARGET/statusline.py"
python3 "$TARGET/tokenmeter.py" --version >/dev/null || { echo "  the engine will not run under this python3"; exit 1; }
say "engine installed in $TARGET"

# 3. Claude Code extras: the /tokenmeter command and the status line
if [ -d "$CLAUDE_DIR" ]; then
    mkdir -p "$CLAUDE_DIR/commands"
    cp "$SRC/commands/tokenmeter.md" "$CLAUDE_DIR/commands/tokenmeter.md"
    say "/tokenmeter command installed"
    statusline_edit "$STATUSLINE"
else
    say "no Claude Code folder found, so no status line or /tokenmeter command"
fi

# 4. The menu bar app
if [ "$APP_WANTED" = 0 ]; then
    say "menu bar app skipped (--no-app)"
elif command -v swiftc >/dev/null 2>&1; then
    "$SRC/costbar/build.sh" >/dev/null 2>&1 && say "menu bar app built: $APP"
    if ! launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
        "$SRC/costbar/install-login-item.sh" >/dev/null 2>&1 && say "menu bar app starts at login"
    fi
else
    say "swiftc not found, so the menu bar app was skipped."
    say "  install it with: xcode-select --install, then run this again"
fi

# 5. What it found
python3 "$TARGET/tokenmeter.py" --list-adapters

echo "Try:"
echo "  python3 $TARGET/tokenmeter.py"
echo "  python3 $TARGET/tokenmeter.py --html"
echo
