#!/usr/bin/env python3
"""GTK4 frontend of neutrino-remote: neutrino-remote-gtk.py [HOST]"""

import os
import sys
import urllib.parse

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Soup", "3.0")
from gi.repository import Gdk, Gio, GLib, GObject, Graphene, Gsk, Gtk, Soup  # noqa: E402

_here = os.path.dirname(os.path.realpath(__file__))
sys.path[:0] = [_here, os.path.join(os.path.dirname(_here), "src")]
import remote  # noqa: E402

APP_ID = "de.flk.NeutrinoRemote"

CSS = """
window, .view, list, listview, scrolledwindow { background-color: #191c22; color: #d7dce5; }
headerbar { background-color: #21252d; color: #d7dce5; box-shadow: none; border-bottom: 1px solid #333a47; }
entry { background-color: #272c36; color: #d7dce5; }
.status { color: #8b95a6; padding: 4px 8px; }
.error { color: #e79a9a; }
.current { color: #67aee8; font-weight: bold; }
.number { color: #8b95a6; font-family: monospace; }
"""


class RemoteView(Gtk.Widget):
    """The remote control picture; a click on a key area sends that key."""

    __gsignals__ = {"key": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def __init__(self):
        super().__init__()
        self.texture = None
        self.areas = []
        self.hot = None
        self.flash = None
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_focusable(True)
        click = Gtk.GestureClick()
        click.connect("pressed", self.on_pressed)
        self.add_controller(click)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self.on_motion)
        motion.connect("leave", lambda *_: self.set_hot(None))
        self.add_controller(motion)
        self.set_has_tooltip(True)
        self.connect("query-tooltip", self.on_tooltip)

    def set_remote(self, texture, areas):
        self.texture, self.areas, self.hot = texture, areas, None
        self.queue_resize()

    def geometry(self):
        w, h = self.get_width(), self.get_height()
        tw, th = self.texture.get_width(), self.texture.get_height()
        scale = min(w / tw, h / th)
        return scale, (w - tw * scale) / 2, (h - th * scale) / 2

    def area_at(self, x, y):
        if not self.texture:
            return None
        scale, ox, oy = self.geometry()
        px, py = (x - ox) / scale, (y - oy) / scale
        for area in self.areas:
            if remote.area_contains(area, px, py):
                return area
        return None

    def set_hot(self, area):
        if area is not self.hot:
            self.hot = area
            self.set_cursor_from_name("pointer" if area else None)
            self.queue_draw()

    def on_motion(self, _ctl, x, y):
        self.set_hot(self.area_at(x, y))

    def on_tooltip(self, _w, x, y, _kb, tooltip):
        area = self.area_at(x, y)
        if not area:
            return False
        tooltip.set_text(area["title"])
        return True

    def on_pressed(self, _gesture, _n, x, y):
        self.grab_focus()
        area = self.area_at(x, y)
        if area:
            self.press(area)

    def press(self, area):
        self.flash = area
        self.queue_draw()
        GLib.timeout_add(150, self.unflash, area)
        self.emit("key", area["key"])

    def press_key(self, key):
        for area in self.areas:
            if area["key"] == key:
                self.flash = area
                self.queue_draw()
                GLib.timeout_add(150, self.unflash, area)
                break
        self.emit("key", key)

    def unflash(self, area):
        if self.flash is area:
            self.flash = None
            self.queue_draw()
        return False

    def do_measure(self, orientation, _for_size):
        if not self.texture:
            return 120, 200, -1, -1
        if orientation == Gtk.Orientation.HORIZONTAL:
            return self.texture.get_width() // 2, self.texture.get_width(), -1, -1
        return self.texture.get_height() // 2, self.texture.get_height(), -1, -1

    def do_snapshot(self, snapshot):
        if not self.texture:
            return
        scale, ox, oy = self.geometry()
        rect = Graphene.Rect().init(ox, oy, self.texture.get_width() * scale,
                                    self.texture.get_height() * scale)
        snapshot.append_scaled_texture(self.texture, Gsk.ScalingFilter.TRILINEAR, rect)
        for area, rgba in ((self.hot, "rgba(103,174,232,0.25)"), (self.flash, "rgba(103,174,232,0.6)")):
            if not area:
                continue
            x, y, w, h = remote.area_bounds(area)
            color = Gdk.RGBA()
            color.parse(rgba)
            r = Graphene.Rect().init(ox + x * scale, oy + y * scale, w * scale, h * scale)
            if area["shape"] == "circle":
                rounded = Gsk.RoundedRect()
                rounded.init_from_rect(r, w * scale / 2)
                snapshot.push_rounded_clip(rounded)
                snapshot.append_color(color, r)
                snapshot.pop()
            else:
                snapshot.append_color(color, r)


class Window(Gtk.ApplicationWindow):
    def __init__(self, app, host, side):
        super().__init__(application=app, title="Neutrino Remote")
        self.aspect = 188 / 762
        self.connect("map", self.on_map)
        self.session = Soup.Session(timeout=5)
        self.host = host
        self.base = remote.base_url(host)

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        self.entry = Gtk.Entry(text=host, placeholder_text="Box address", width_chars=12, hexpand=True)
        self.entry.set_tooltip_text("IP address or host name of the Neutrino box")
        self.entry.connect("activate", lambda *_: self.connect_to(self.entry.get_text()))
        header.set_title_widget(self.entry)
        self.list_button = Gtk.ToggleButton(icon_name="view-list-symbolic")
        self.list_button.set_tooltip_text("Channel list")
        self.list_button.connect("toggled", self.on_list_toggled)
        header.pack_end(self.list_button)

        self.view = RemoteView()
        self.view.connect("key", lambda _v, key: self.send_key(key))
        self.status = Gtk.Label(xalign=0, ellipsize=3)
        self.status.add_css_class("status")

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        left.append(self.view)
        left.append(self.status)

        self.bouquets = Gtk.DropDown.new_from_strings([])
        self.bouquets.connect("notify::selected", self.on_bouquet)
        self.bouquet_numbers = []
        self.channel_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.channel_list.connect("row-activated", self.on_channel)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(self.channel_list)
        self.side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, width_request=260)
        self.side.append(self.bouquets)
        self.side.append(scroll)
        self.side.set_visible(False)

        box = Gtk.Box(spacing=6)
        box.append(left)
        if side == "right":
            box.append(self.side)
        else:
            box.prepend(self.side)
        self.set_child(box)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)

        self.connect_to(host)

    def on_map(self, *_):
        self.fit_to_monitor()
        self.set_focus(self.view)

    def monitor(self):
        display = self.get_display()
        surface = self.get_surface()
        mon = display.get_monitor_at_surface(surface) if surface else None
        if mon is None:
            monitors = display.get_monitors()
            mon = monitors.get_item(0) if monitors.get_n_items() else None
        return mon

    def fit_to_monitor(self):
        mon = self.monitor()
        if mon is None:
            return
        area = mon.get_geometry()
        header = 48
        view_h = int(area.height * 0.6) - header
        width = max(260, int(view_h * self.aspect) + 24)
        if self.side.get_visible():
            side = max(280, int(area.width * 0.15))
            self.side.set_size_request(side, -1)
            width += side + 6
        self.set_default_size(width, view_h + header)

    def get(self, path, callback, raw=False, quiet=False):
        msg = Soup.Message.new("GET", urllib.parse.urljoin(self.base, path))
        if msg is None:
            self.show_status("Invalid address", True)
            return

        def done(session, result):
            try:
                data = session.send_and_read_finish(result).get_data()
                if msg.get_status() != 200:
                    raise GLib.Error(f"HTTP {msg.get_status()}")
            except GLib.Error as err:
                if not quiet:
                    self.show_status(f"{self.host}: {err.message}", True)
                callback(None)
                return
            callback(data if raw else data.decode("utf-8", "replace"))

        self.session.send_and_read_async(msg, GLib.PRIORITY_DEFAULT, None, done)

    def show_status(self, text, error=False):
        self.status.set_text(text)
        (self.status.add_css_class if error else self.status.remove_css_class)("error")

    def connect_to(self, host):
        host = host.strip()
        if not host:
            return
        self.host, self.base = host, remote.base_url(host)
        remote.save_host(host)
        self.show_status(f"Connecting to {host} ...")
        self.get("Y_Tools_Rcsim.yhtm", self.on_page)

    def on_page(self, html):
        if html is None:
            self.show_cached()
            return
        parsed = remote.parse_remote(html, self.base)
        if not parsed:
            self.show_status(f"{self.host}: no remote control in the web interface", True)
            return

        def on_image(data):
            if data is None:
                self.show_cached()
                return
            if not self.show_remote(data, parsed["areas"]):
                return
            remote.save_cache(self.host, parsed["areas"], data)
            self.show_status(f"Connected to {self.host}")
            if self.side.get_visible():
                self.load_bouquets()

        self.get(parsed["image"], on_image, raw=True)

    def show_remote(self, data, areas):
        try:
            texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
        except GLib.Error as err:
            self.show_status(f"Remote control picture: {err.message}", True)
            return False
        self.view.set_remote(texture, areas)
        self.aspect = texture.get_width() / texture.get_height()
        self.fit_to_monitor()
        self.set_focus(self.view)
        return True

    def show_cached(self):
        cached = remote.load_cache(self.host)
        if cached and self.show_remote(cached[1], cached[0]):
            self.show_status(f"{self.host}: not reachable, last remote shown", True)

    def send_key(self, key):
        if key == "KEY_POWER":
            self.get("control/standby", lambda state: self.confirm_power(state))
            return
        self.get("control/rcem?" + key, lambda r: r is not None and self.show_status(f"{key[4:]} sent"))

    def confirm_power(self, state):
        if state is None:
            self.start_local()
            return
        if state.strip() != "off":
            self.get("control/rcem?KEY_POWER", lambda r: r is not None and self.show_status("POWER sent"))
            return
        dialog = Gtk.AlertDialog(message="Put the box into standby?", buttons=["Cancel", "Standby"],
                                 cancel_button=0, default_button=1)

        def answered(d, result):
            try:
                if d.choose_finish(result) == 1:
                    self.get("control/rcem?KEY_POWER", lambda r: r is not None and self.show_status("POWER sent"))
            except GLib.Error:
                pass

        dialog.choose(self, None, answered)

    def start_local(self):
        command = remote.local_start_command() if remote.is_local(self.host) else None
        if not command:
            return
        try:
            Gio.Subprocess.new(command, Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE)
        except GLib.Error as err:
            self.show_status(f"{remote.LOCAL_PROGRAM}: {err.message}", True)
            return
        self.show_status("Starting Neutrino ...")
        self.retries = 15
        GLib.timeout_add_seconds(2, self.retry_connect)

    def retry_connect(self):
        self.retries -= 1

        def done(state):
            if state is not None:
                self.connect_to(self.host)
            elif self.retries > 0:
                GLib.timeout_add_seconds(2, self.retry_connect)
            else:
                self.show_status("Neutrino did not come up", True)

        self.get("control/standby", done, quiet=True)
        return False

    def on_key(self, _ctl, keyval, _code, state):
        if self.entry.has_focus() or state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False
        key = remote.KEYBOARD.get(Gdk.keyval_name(keyval))
        if not key:
            return False
        self.view.press_key(key)
        return True

    def on_list_toggled(self, button):
        self.side.set_visible(button.get_active())
        self.fit_to_monitor()
        if button.get_active():
            self.load_bouquets()

    def load_bouquets(self):
        def done(text):
            if text is None:
                return
            try:
                bouquets = remote.parse_bouquets(text)
            except (ValueError, KeyError):
                self.show_status("Bouquet list not readable", True)
                return
            self.bouquet_numbers = [number for number, _ in bouquets]
            self.bouquets.set_model(Gtk.StringList.new([name for _, name in bouquets]))
            if bouquets:
                self.bouquets.set_selected(0)
                self.on_bouquet()

        self.get("control/getbouquets?format=json", done)

    def on_bouquet(self, *_):
        index = self.bouquets.get_selected()
        if index >= len(self.bouquet_numbers):
            return
        number = self.bouquet_numbers[index]

        def done(text):
            if text is None:
                return
            try:
                channels = remote.parse_channels(text)
            except (ValueError, KeyError):
                self.show_status("Channel list not readable", True)
                return
            self.get("control/zapto", lambda current: self.fill_channels(channels, (current or "").strip()))

        self.get(f"control/getbouquet?bouquet={number}&format=json", done)

    def fill_channels(self, channels, current):
        self.channel_list.remove_all()
        for number, cid, name in channels:
            row = Gtk.ListBoxRow()
            row.channel_id = cid
            box = Gtk.Box(spacing=8, margin_start=6, margin_end=6, margin_top=3, margin_bottom=3)
            num = Gtk.Label(label=number, width_chars=4, xalign=1)
            num.add_css_class("number")
            label = Gtk.Label(label=name, xalign=0, ellipsize=3, hexpand=True)
            if cid == current:
                label.add_css_class("current")
            box.append(num)
            box.append(label)
            row.set_child(box)
            self.channel_list.append(row)

    def on_channel(self, _list, row):
        def done(result):
            if result is None:
                return
            self.show_status("Switched channel")
            child = self.channel_list.get_first_child()
            while child:
                label = child.get_child().get_last_child()
                (label.add_css_class if child is row else label.remove_css_class)("current")
                child = child.get_next_sibling()

        self.get("control/zapto?" + row.channel_id, done)


class App(Gtk.Application):
    def __init__(self, host, side):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.host = host
        self.side = side

    def do_activate(self):
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Window(self, self.host, self.side).present()


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else remote.load_host()
    side = sys.argv[3] if len(sys.argv) > 3 else remote.load_side()
    return App(host, side).run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
