#!/bin/bash
# Matrix Live Wallpaper — per-user installer (no sudo needed).
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
APPDIR="${XDG_DATA_HOME:-$HOME/.local/share}/matrix-wallpaper"
BINDIR="$HOME/.local/bin"
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
EXT_UUID="matrix-wallpaper-below@matrix-wallpaper"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*"; }

bold "Matrix Live Wallpaper installer"
echo

# ---- 1. environment checks -------------------------------------------------
if [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
    warn "You are on a Wayland session. The wallpaper only runs on X11."
    warn "It will be installed anyway and will work when you log into an"
    warn "'Xorg'/'X11' session (choose it from the gear menu on the login screen)."
    echo
fi

if ! python3 - <<'EOF' 2>/dev/null
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gst", "1.0")
gi.require_version("GstVideo", "1.0")
from gi.repository import Gtk, Gst
EOF
then
    warn "Missing Python GTK/GStreamer bindings. Install them with:"
    echo "  Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gst-plugins-base-1.0 \\"
    echo "                   gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-libav gstreamer1.0-gl"
    echo "  Fedora:        sudo dnf install python3-gobject gtk3 gstreamer1-plugins-base \\"
    echo "                   gstreamer1-plugins-good gstreamer1-libav"
    echo "  Arch:          sudo pacman -S python-gobject gtk3 gst-plugins-base gst-plugins-good gst-libav"
    echo
    echo "Then run ./install.sh again."
    exit 1
fi

# non-fatal decoder sanity check
if ! python3 - <<'EOF' 2>/dev/null
import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst
Gst.init(None)
assert Gst.ElementFactory.find("playbin")
assert Gst.ElementFactory.find("qtdemux")
assert any(Gst.ElementFactory.find(d) for d in
           ("nvh264dec", "vah264dec", "vaapih264dec", "avdec_h264", "openh264dec"))
EOF
then
    warn "Warning: no H.264 decoder found in GStreamer. If the wallpaper stays"
    warn "black, install your distro's 'gstreamer libav / plugins-good' packages."
    echo
fi

# ---- 2. install files --------------------------------------------------------
echo "Installing to $APPDIR"
mkdir -p "$APPDIR" "$BINDIR" "$AUTOSTART"
# stop any running copy (old or new install locations)
pkill -f "matrix-wallpaper/player\.py" 2>/dev/null || true
sleep 0.5

install -m 644 "$SRC/matrix_loop.mp4"    "$APPDIR/matrix_loop.mp4"
install -m 755 "$SRC/player.py"          "$APPDIR/player.py"
install -m 644 "$SRC/render_matrix.py"   "$APPDIR/render_matrix.py"
install -m 644 "$SRC/README.md"          "$APPDIR/README.md"
install -m 755 "$SRC/uninstall.sh"       "$APPDIR/uninstall.sh"
install -m 755 "$SRC/bin/matrix-wallpaper" "$BINDIR/matrix-wallpaper"

cat > "$AUTOSTART/matrix-wallpaper.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Matrix Wallpaper
Comment=Matrix digital-rain live wallpaper
Exec=$BINDIR/matrix-wallpaper on
X-GNOME-Autostart-enabled=true
EOF

case ":$PATH:" in
  *":$BINDIR:"*) ;;
  *) warn "Note: $BINDIR is not in your PATH; use the full path or add it." ;;
esac

# ---- 3. GNOME Shell extension (keeps the video under the desktop icons) -----
NEED_RELOGIN=""
if command -v gnome-shell >/dev/null 2>&1; then
    SHELL_MAJOR="$(gnome-shell --version | grep -oE '[0-9]+' | head -1)"
    if [ "${SHELL_MAJOR:-0}" -ge 45 ]; then
        EXTDIR="$HOME/.local/share/gnome-shell/extensions/$EXT_UUID"
        echo "Installing GNOME Shell extension ($EXT_UUID, shell $SHELL_MAJOR)"
        mkdir -p "$EXTDIR"
        install -m 644 "$SRC/extension/extension.js" "$EXTDIR/extension.js"
        cat > "$EXTDIR/metadata.json" <<EOF
{
    "uuid": "$EXT_UUID",
    "name": "Matrix Wallpaper Below",
    "description": "Keeps the matrix-wallpaper video window below the desktop icons window.",
    "shell-version": ["$SHELL_MAJOR"]
}
EOF
        python3 - <<EOF
import ast, subprocess
uuid = "$EXT_UUID"
cur = subprocess.check_output(
    ["gsettings", "get", "org.gnome.shell", "enabled-extensions"]).decode().strip()
lst = [] if cur == "@as []" else list(ast.literal_eval(cur))
if uuid not in lst:
    lst.append(uuid)
    subprocess.check_call(
        ["gsettings", "set", "org.gnome.shell", "enabled-extensions", str(lst)])
EOF
        # loads only after the shell rescans extensions
        if ! gnome-extensions info "$EXT_UUID" >/dev/null 2>&1; then
            NEED_RELOGIN=yes
        fi
    else
        warn "GNOME Shell $SHELL_MAJOR is older than 45; skipping the helper"
        warn "extension. If desktop icons hide behind the rain, disable the"
        warn "icons extension or upgrade GNOME."
    fi
fi

# ---- 4. start ---------------------------------------------------------------
if [ "${XDG_SESSION_TYPE:-x11}" != "wayland" ] && [ -n "${DISPLAY:-}" ]; then
    "$BINDIR/matrix-wallpaper" on
fi

echo
bold "Done."
echo "  control:   matrix-wallpaper on|off|toggle|status"
echo "  autostart: installed (runs at login)"
echo "  uninstall: $APPDIR/uninstall.sh"
if [ -n "$NEED_RELOGIN" ]; then
    echo
    warn "GNOME: log out and back in once (or on X11 press Alt+F2, type 'r', Enter)"
    warn "so the desktop-icons helper extension loads. Until then your desktop"
    warn "icons may hide behind the rain."
fi
