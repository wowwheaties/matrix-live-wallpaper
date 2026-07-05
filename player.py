#!/usr/bin/env python3
"""Matrix live wallpaper: plays a looping rain video on a DESKTOP-layer window.

- GTK window with DESKTOP type hint, managed by the window manager, which
  pins it to the desktop layer: below every normal window, hidden from the
  taskbar and overview.
- GStreamer playbin picks the best available decoder (NVDEC/VAAPI/software);
  the 30fps video only forces 30 repaints/s regardless of monitor refresh.
- Loops gaplessly via segment seeks (no flash at the seam).
- On GNOME, the bundled matrix-wallpaper-below shell extension keeps this
  window under the desktop-icons window (see extension/ in the source).
"""
import os
import sys

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gst", "1.0")
gi.require_version("GstVideo", "1.0")
gi.require_version("GdkX11", "3.0")
from gi.repository import Gtk, Gdk, GdkX11, GLib, Gst, GstVideo  # noqa: E402

VIDEO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "matrix_loop.mp4")

Gst.init(None)


class Wallpaper:
    def __init__(self):
        self.win = Gtk.Window(title="matrix-wallpaper")
        self.win.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
        self.win.set_decorated(False)
        self.win.set_skip_taskbar_hint(True)
        self.win.set_skip_pager_hint(True)
        self.win.set_accept_focus(False)
        # NEVER set_keep_below() here: _NET_WM_STATE_BELOW moves the window
        # from mutter's DESKTOP layer up into the BOTTOM layer, above the
        # desktop-icons window, and no restack can cross layers.
        screen = Gdk.Screen.get_default()
        self.win.move(0, 0)
        self.win.set_default_size(screen.get_width(), screen.get_height())
        self.win.connect("realize", self.on_realize)
        self.win.connect("delete-event", Gtk.main_quit)

        self.xid = None
        self.play = Gst.ElementFactory.make("playbin", None)
        self.play.set_property("uri", "file://" + VIDEO)
        sink = Gst.ElementFactory.make("glimagesink", None)
        if sink is not None:
            sink.set_property("handle-events", False)
            self.play.set_property("video-sink", sink)
        # mute even though the file has no audio track
        self.play.set_property("volume", 0.0)

        bus = self.play.get_bus()
        bus.add_signal_watch()
        bus.enable_sync_message_emission()
        bus.connect("sync-message::element", self.on_sync_message)
        bus.connect("message::segment-done", self.on_segment_done)
        bus.connect("message::eos", self.on_eos)
        bus.connect("message::error", self.on_error)

    def on_realize(self, widget):
        gdkwin = widget.get_window()
        gdkwin.set_events(Gdk.EventMask.EXPOSURE_MASK)  # ignore clicks entirely
        self.xid = gdkwin.get_xid()
        self.win.get_window().lower()
        self.play.set_state(Gst.State.PLAYING)
        # start the gapless segment loop once preroll finishes
        GLib.timeout_add(500, self.start_segment_loop)
        GLib.timeout_add_seconds(5, self.keep_below)

    def keep_below(self):
        # Best-effort re-lower for non-GNOME WMs; on GNOME the shell
        # extension owns the ordering (client lowers are ignored there).
        w = self.win.get_window()
        if w is not None:
            w.lower()
        return True

    def start_segment_loop(self):
        # The seek is rejected until preroll completes; on a busy login
        # (many apps starting at once) 500ms is not always enough, and a
        # missed seek means playback runs to EOS and freezes on the last
        # frame. Keep retrying until the pipeline accepts it.
        ok = self.play.seek(1.0, Gst.Format.TIME,
                            Gst.SeekFlags.FLUSH | Gst.SeekFlags.SEGMENT,
                            Gst.SeekType.SET, 0, Gst.SeekType.NONE, -1)
        return not ok

    def on_segment_done(self, bus, msg):
        self.play.seek(1.0, Gst.Format.TIME, Gst.SeekFlags.SEGMENT,
                       Gst.SeekType.SET, 0, Gst.SeekType.NONE, -1)

    def on_eos(self, bus, msg):
        # Safety net: EOS only arrives when the segment loop was never
        # armed (or dropped) — restart playback from 0 and re-arm it.
        self.play.seek(1.0, Gst.Format.TIME,
                       Gst.SeekFlags.FLUSH | Gst.SeekFlags.SEGMENT,
                       Gst.SeekType.SET, 0, Gst.SeekType.NONE, -1)

    def on_sync_message(self, bus, msg):
        if msg.get_structure() and msg.get_structure().get_name() == "prepare-window-handle":
            msg.src.set_window_handle(self.xid)

    def on_error(self, bus, msg):
        err, dbg = msg.parse_error()
        print("gst error:", err, dbg, file=sys.stderr)
        Gtk.main_quit()

    def run(self):
        self.win.stick()
        self.win.show_all()
        Gtk.main()


def main():
    if not os.path.exists(VIDEO):
        sys.exit(f"matrix-wallpaper: video not found: {VIDEO}")
    display = Gdk.Display.get_default()
    if display is None or not isinstance(display, GdkX11.X11Display):
        sys.exit("matrix-wallpaper: needs an X11 session "
                 "(on the login screen, pick a session labelled 'Xorg' or 'X11'). "
                 "Wayland is not supported yet.")
    Wallpaper().run()


if __name__ == "__main__":
    main()
