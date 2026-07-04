#!/bin/bash
# Matrix Live Wallpaper — uninstaller
set -e
APPDIR="${XDG_DATA_HOME:-$HOME/.local/share}/matrix-wallpaper"
EXT_UUID="matrix-wallpaper-below@matrix-wallpaper"

pkill -f "matrix-wallpaper/player\.py" 2>/dev/null || true

rm -f  "$HOME/.local/bin/matrix-wallpaper"
rm -f  "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/matrix-wallpaper.desktop"
rm -rf "$HOME/.local/share/gnome-shell/extensions/$EXT_UUID"

if command -v gsettings >/dev/null 2>&1; then
    python3 - <<EOF 2>/dev/null || true
import ast, subprocess
uuid = "$EXT_UUID"
cur = subprocess.check_output(
    ["gsettings", "get", "org.gnome.shell", "enabled-extensions"]).decode().strip()
lst = [] if cur == "@as []" else list(ast.literal_eval(cur))
if uuid in lst:
    lst.remove(uuid)
    subprocess.check_call(
        ["gsettings", "set", "org.gnome.shell", "enabled-extensions", str(lst)])
EOF
fi

rm -rf "$APPDIR"
echo "Matrix Live Wallpaper removed."
