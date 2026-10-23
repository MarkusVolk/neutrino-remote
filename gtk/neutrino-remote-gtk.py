#!/usr/bin/env python3
"""GTK4 frontend of neutrino-remote: neutrino-remote-gtk.py [HOST]"""

import json
import os
import sys
import time
import urllib.parse

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Soup", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Gio, GLib, GObject, Graphene, Gsk, Gtk, Pango, Soup  # noqa: E402

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
.epg { color: #8b95a6; font-size: smaller; }
progressbar.epg trough, progressbar.epg progress { min-height: 3px; }
progressbar.epg trough { background-color: #333a47; }
remoteview { font-size: 9pt; }
progressbar.epg progress { background-color: #67aee8; }
paned > separator { background: #333a47; min-height: 1px; opacity: 0; }
paned > separator:hover { opacity: 1; }
"""

SNI_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <method name="Activate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="SecondaryActivate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="ContextMenu"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="Scroll"><arg name="delta" type="i" direction="in"/><arg name="orientation" type="s" direction="in"/></method>
  </interface>
</node>
"""
WATCHER = "org.kde.StatusNotifierWatcher"
TRAY_ICON = APP_ID + "-symbolic"


def tray_icon_dir():
    """Where the tray icon is: installed next to the program, or data/ of the source tree."""
    share = os.path.dirname(_here)
    for d in (os.path.join(share, "icons", "hicolor", "symbolic", "apps"), os.path.join(share, "data")):
        if os.path.exists(os.path.join(d, TRAY_ICON + ".svg")):
            return d
    return ""


class Tray:
    """An icon in the panel's tray (StatusNotifierItem); a click on it calls on_activate."""

    def __init__(self, on_activate):
        self.on_activate = on_activate
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        self.name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self.info = Gio.DBusNodeInfo.new_for_xml(SNI_XML).interfaces[0]
        self.object_id = 0
        self.owner_id = 0

    def available(self):
        try:
            reply = self.bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                                       "NameHasOwner", GLib.Variant("(s)", (WATCHER,)), None,
                                       Gio.DBusCallFlags.NONE, -1, None)
            return reply.unpack()[0]
        except GLib.Error:
            return False

    def show(self):
        if self.object_id:
            return
        self.object_id = self.bus.register_object("/StatusNotifierItem", self.info, self.on_call, self.on_property)
        self.owner_id = Gio.bus_own_name_on_connection(self.bus, self.name, Gio.BusNameOwnerFlags.NONE, None, None)
        self.bus.call(WATCHER, "/StatusNotifierWatcher", WATCHER, "RegisterStatusNotifierItem",
                      GLib.Variant("(s)", (self.name,)), None, Gio.DBusCallFlags.NONE, -1, None, None)

    def hide(self):
        if self.owner_id:
            Gio.bus_unown_name(self.owner_id)
            self.owner_id = 0
        if self.object_id:
            self.bus.unregister_object(self.object_id)
            self.object_id = 0

    def on_property(self, _bus, _sender, _path, _iface, prop):
        return {
            "Category": GLib.Variant("s", "ApplicationStatus"),
            "Id": GLib.Variant("s", "neutrino-remote"),
            "Title": GLib.Variant("s", "Neutrino Remote"),
            "Status": GLib.Variant("s", "Active"),
            "IconName": GLib.Variant("s", TRAY_ICON),
            "IconThemePath": GLib.Variant("s", tray_icon_dir()),
            "ItemIsMenu": GLib.Variant("b", False),
            "Menu": GLib.Variant("o", "/NO_DBUSMENU"),
        }.get(prop)

    def on_call(self, _bus, _sender, _path, _iface, method, _params, invocation):
        invocation.return_value(None)
        if method in ("Activate", "SecondaryActivate", "ContextMenu"):
            self.on_activate()


class RemoteView(Gtk.Widget):
    """The remote control, drawn from a layout; a click on a key sends it."""

    __gsignals__ = {"key": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    BODY = "#272c36"
    BUTTON = "#3a4150"
    LABEL = "#d7dce5"

    def __init__(self):
        super().__init__()
        self.set_css_name("remoteview")
        self.canvas = None
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

    def set_drawn(self, layout):
        self.hot = None
        self.canvas = (layout["width"], layout["height"])
        self.areas = layout["keys"]
        self.queue_resize()

    def geometry(self):
        w, h = self.get_width(), self.get_height()
        tw, th = self.canvas
        scale = min(w / tw, h / th)
        return scale, (w - tw * scale) / 2, (h - th * scale) / 2

    def area_at(self, x, y):
        if not self.canvas:
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
        if not self.canvas:
            return 120, 200, -1, -1
        tw, th = self.canvas
        if orientation == Gtk.Orientation.HORIZONTAL:
            return tw // 2, tw, -1, -1
        return th // 2, th, -1, -1

    @staticmethod
    def rgba(spec):
        color = Gdk.RGBA()
        color.parse(spec)
        return color

    def rounded(self, snapshot, rect, radius, color):
        clip = Gsk.RoundedRect()
        clip.init_from_rect(rect, radius)
        snapshot.push_rounded_clip(clip)
        snapshot.append_color(color, rect)
        snapshot.pop()

    def draw_keys(self, snapshot, scale, ox, oy):
        tw, th = self.canvas
        self.rounded(snapshot, Graphene.Rect().init(ox, oy, tw * scale, th * scale), 24 * scale, self.rgba(self.BODY))
        theme = Gtk.IconTheme.get_for_display(self.get_display())
        label_color = self.rgba(self.LABEL)
        for area in self.areas:
            x, y, w, h = remote.area_bounds(area)
            r = Graphene.Rect().init(ox + x * scale, oy + y * scale, w * scale, h * scale)
            radius = w * scale / 2 if area["shape"] == "circle" else 5 * scale
            self.rounded(snapshot, r, radius, self.rgba(area.get("color", self.BUTTON)))
            if area.get("icon"):
                size = int(min(w, h) * scale * 0.55)
                icon = theme.lookup_icon(area["icon"], None, max(size, 8), self.get_scale_factor(),
                                         Gtk.TextDirection.NONE, 0)
                snapshot.save()
                snapshot.translate(Graphene.Point().init(r.get_x() + (r.get_width() - size) / 2,
                                                         r.get_y() + (r.get_height() - size) / 2))
                icon.snapshot_symbolic(snapshot, size, size, [label_color])
                snapshot.restore()
            elif area.get("label"):
                layout = self.create_pango_layout(area["label"])
                font = layout.get_context().get_font_description() or Pango.FontDescription()
                font.set_absolute_size(min(h * 0.45, 13) * scale * Pango.SCALE)
                layout.set_font_description(font)
                lw, lh = layout.get_pixel_size()
                snapshot.save()
                snapshot.translate(Graphene.Point().init(r.get_x() + (r.get_width() - lw) / 2,
                                                         r.get_y() + (r.get_height() - lh) / 2))
                snapshot.append_layout(layout, label_color)
                snapshot.restore()

    def do_snapshot(self, snapshot):
        if not self.canvas:
            return
        scale, ox, oy = self.geometry()
        self.draw_keys(snapshot, scale, ox, oy)
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
        self.login_dialog = None
        self.waiting = []
        self.host = host
        self.base = remote.base_url(host)
        self.api = remote.API

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        self.entry = Gtk.Entry(text=host, placeholder_text="Box address", width_chars=15, hexpand=True)
        self.entry.set_tooltip_text("IP address or host name of the Neutrino box")
        self.entry.connect("activate", lambda *_: self.connect_to(self.entry.get_text()))
        header.set_title_widget(self.entry)
        self.list_button = Gtk.ToggleButton(icon_name="view-list-symbolic")
        self.list_button.set_tooltip_text("Channel list")
        self.list_button.connect("toggled", self.on_list_toggled)
        self.epg_timer = 0
        self.tray = Tray(self.restore)
        if self.tray.available():
            tray_button = Gtk.Button(icon_name="go-down-symbolic")
            tray_button.set_tooltip_text("Minimize to the tray")
            tray_button.connect("clicked", lambda *_: self.to_tray())
            header.pack_end(tray_button)
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
        self.bouquet_web = []
        self.channel_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.channel_list.connect("row-activated", self.on_channel)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(self.channel_list)
        self.side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, width_request=260)
        self.side.append(self.bouquets)
        self.osd = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True)
        self.osd.set_tooltip_text("Screen of the box")
        self.osd_frame = Gtk.AspectFrame(ratio=16 / 9, obey_child=False, visible=False)
        self.osd_frame.set_child(self.osd)
        self.split = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL, vexpand=True,
                               shrink_start_child=False, shrink_end_child=True)
        self.split.set_start_child(scroll)
        self.split.set_end_child(self.osd_frame)
        self.split_placed = False
        self.side.append(self.split)
        self.side.set_visible(False)
        self.osd_timers = []
        self.osd_busy = False
        self.osd_again = False

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

    def to_tray(self):
        self.tray.show()
        self.set_visible(False)

    def restore(self):
        self.tray.hide()
        self.present()

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
        self.view.set_size_request(width if self.side.get_visible() else -1, -1)
        if self.side.get_visible():
            side = max(320, int(area.width * 0.25))
            self.side.set_size_request(side, -1)
            width += side + 6
            if not self.split_placed:
                list_h = view_h - 48 - side * 9 // 16
                self.split.set_position(max(list_h, view_h * 3 // 10))
                self.split_placed = True
        self.set_default_size(width, view_h + header)

    def get(self, path, callback, raw=False, quiet=False):
        self.request("GET", path, None, callback, raw, quiet)

    def post(self, path, body, callback, quiet=False):
        self.request("POST", path, body, callback, False, quiet)

    def send(self, req, callback, quiet=False):
        method, path, body = req
        self.request(method, path, body, callback, False, quiet)

    def request(self, method, path, body, callback, raw=False, quiet=False, retried=False):
        msg = Soup.Message.new(method, urllib.parse.urljoin(self.base, path))
        if msg is None:
            self.show_status("Invalid address", True)
            return
        headers = msg.get_request_headers()
        token = remote.load_token(self.host)
        login = None if token else remote.load_session(self.host)
        if token:
            headers.append("Authorization", "Bearer " + token)
        elif login:
            headers.append("Cookie", f"{remote.SESSION_COOKIE}={login[0]}")
            if method != "GET":
                headers.append(remote.CSRF_HEADER, login[1])
        if body is not None:
            msg.set_request_body_from_bytes("application/json", GLib.Bytes.new(json.dumps(body).encode()))

        def done(session, result):
            try:
                data = session.send_and_read_finish(result).get_data()
                if (msg.get_status() == 403 and self.api == remote.API and not retried
                        and path.startswith("api/v1/")):
                    if token:
                        remote.clear_token(self.host)
                    elif login:
                        remote.clear_session(self.host)
                    self.sign_in(lambda ok: self.request(method, path, body, callback, raw, quiet, True)
                                 if ok else callback(None), token_refused=bool(token))
                    return
                if msg.get_status() // 100 != 2:
                    raise GLib.Error(f"HTTP {msg.get_status()}")
            except GLib.Error as err:
                if not quiet:
                    self.show_status(f"{self.host}: {err.message}", True)
                callback(None)
                return
            callback(data if raw else data.decode("utf-8", "replace"))

        self.session.send_and_read_async(msg, GLib.PRIORITY_DEFAULT, None, done)

    def sign_in(self, then, token_refused=False):
        """A box that wants a sign-in for this asks for its name and password, or for a
        token it knows; what it answers with, or the token, is kept for the box, the
        password is not. Requests that come in while the dialog is open wait for it."""
        self.waiting.append(then)
        if self.login_dialog:
            return
        dialog = Gtk.Window(title=f"Sign in to {self.host}", transient_for=self, modal=True,
                            resizable=False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12,
                      margin_bottom=12, margin_start=12, margin_end=12)
        user = Gtk.Entry(text=remote.LOGIN_USER, placeholder_text="Name")
        password = Gtk.PasswordEntry(placeholder_text="Password", show_peek_icon=True)
        note = Gtk.Label(label="The box did not take the token." if token_refused
                         else "The box asks for a sign-in to be controlled.", xalign=0, wrap=True,
                         max_width_chars=30)
        note.add_css_class("status")
        if token_refused:
            note.add_css_class("error")
        buttons = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        ok = Gtk.Button(label="Sign in")
        ok.add_css_class("suggested-action")
        buttons.append(cancel)
        buttons.append(ok)

        token_note = Gtk.Label(label="Or with a token the box knows, which lasts beyond a restart of the box:",
                               xalign=0, wrap=True, max_width_chars=30)
        token_note.add_css_class("status")
        token = Gtk.Entry(placeholder_text="Token", hexpand=True, width_chars=12)
        generate = Gtk.Button(label="Generate")
        generate.set_tooltip_text("A new token, to be entered on the box")
        token_row = Gtk.Box(spacing=6)
        token_row.append(token)
        token_row.append(generate)
        lines = Gtk.Label(xalign=0, selectable=True, wrap=True, wrap_mode=Pango.WrapMode.CHAR,
                          max_width_chars=30, visible=False)
        lines.add_css_class("epg")
        token_buttons = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        copy = Gtk.Button(label="Copy line", sensitive=False)
        use = Gtk.Button(label="Use token", sensitive=False)
        token_buttons.append(copy)
        token_buttons.append(use)
        for w in (note, user, password, buttons, Gtk.Separator(), token_note, token_row, lines, token_buttons):
            box.append(w)

        def token_changed(*_):
            text = token.get_text().strip()
            lines.set_label(remote.token_lines(text) if text else "")
            lines.set_visible(bool(text))
            copy.set_sensitive(bool(text))
            use.set_sensitive(bool(text))

        token.connect("changed", token_changed)
        generate.connect("clicked", lambda *_: token.set_text(remote.new_token()))
        copy.connect("clicked", lambda *_: self.get_clipboard().set(lines.get_label()))

        def use_token(*_):
            remote.save_token(self.host, token.get_text())
            self.show_status(f"Token kept for {self.host}")
            finish(True)

        use.connect("clicked", use_token)
        token.connect("activate", lambda *_: use.get_sensitive() and use_token())
        dialog.set_child(box)
        dialog.set_default_widget(ok)
        password.connect("activate", lambda *_: submit())
        self.login_dialog = dialog

        def finish(success):
            self.login_dialog = None
            dialog.destroy()
            waiting, self.waiting = self.waiting, []
            for w in waiting:
                w(success)

        def answered(msg, text):
            ok.set_sensitive(True)
            status = msg.get_status()
            if status == 200:
                try:
                    csrf = json.loads(text).get("csrf", "")
                except ValueError:
                    csrf = ""
                cookie = remote.session_cookie(msg.get_response_headers().get_one("Set-Cookie"))
                if cookie and csrf:
                    remote.save_session(self.host, cookie, csrf)
                    self.show_status(f"Signed in to {self.host}")
                    finish(True)
                    return
            note.set_label({401: "Name and password do not go together.",
                            429: "Too many wrong attempts, wait a moment."}.get(status, f"Sign-in failed (HTTP {status})."))
            note.add_css_class("error")

        def submit(*_):
            ok.set_sensitive(False)
            msg = Soup.Message.new("POST", urllib.parse.urljoin(self.base, remote.LOGIN_PATH))
            body = {"user": user.get_text(), "password": password.get_text()}
            msg.set_request_body_from_bytes("application/json", GLib.Bytes.new(json.dumps(body).encode()))

            def done(session, result):
                try:
                    text = session.send_and_read_finish(result).get_data().decode("utf-8", "replace")
                except GLib.Error as err:
                    ok.set_sensitive(True)
                    note.set_label(err.message)
                    note.add_css_class("error")
                    return
                answered(msg, text)

            self.session.send_and_read_async(msg, GLib.PRIORITY_DEFAULT, None, done)

        ok.connect("clicked", submit)
        cancel.connect("clicked", lambda *_: finish(False))
        dialog.connect("close-request", lambda *_: (finish(False), True)[1] if self.login_dialog else False)
        dialog.present()
        password.grab_focus()

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
        self.show_drawn()

    def show_drawn(self):
        """The drawn remote control; whether the box is there, and which API it speaks,
        is asked of it."""
        layout = remote.load_layout()
        if not layout:
            self.show_status("remote-layout.json not found", True)
            return
        self.view.set_drawn(layout)
        self.aspect = layout["width"] / layout["height"]
        self.fit_to_monitor()
        self.set_focus(self.view)

        def answered(api):
            self.api = api
            self.show_status(f"Connected to {self.host}" + ("" if api == remote.API else " (control API)"))
            if self.side.get_visible():
                self.load_bouquets()

        def control(text):
            if text is not None:
                answered(remote.CONTROL)

        def probed(text):
            if text is not None:
                answered(remote.API)
            else:
                self.get(remote.CONTROL_PROBE_PATH, control)

        self.get(remote.PROBE_PATH, probed, quiet=True)

    def send_key(self, key):
        if key == "KEY_POWER":
            self.get(remote.standby_path(self.api), lambda state: self.confirm_power(state))
            return
        self.press(key)

    def press(self, key):
        self.send(remote.key_request(self.api, key), lambda r: r is not None and self.key_sent(key[4:]))

    def key_sent(self, name):
        self.show_status(f"{name} sent")
        self.follow_osd()

    def follow_osd(self):
        """The screen follows the last key of a row: a shot when the keys have stopped
        for a moment, and one more for a channel change."""
        for timer in self.osd_timers:
            GLib.source_remove(timer)
        self.osd_timers = [GLib.timeout_add(ms, self.osd_timeout) for ms in remote.OSD_AFTER_KEY]

    def osd_timeout(self):
        self.osd_timers = self.osd_timers[1:]
        self.grab_osd()
        return False

    def grab_osd(self):
        if not self.side.get_visible():
            return
        if self.osd_busy:
            self.osd_again = True
            return
        self.osd_busy = True

        def shown():
            self.osd_busy = False
            if self.osd_again:
                self.osd_again = False
                self.grab_osd()

        def on_image(data):
            if data:
                try:
                    texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
                except GLib.Error:
                    texture = None
                if texture:
                    pixels, _stride = Gdk.TextureDownloader.new(texture).download_bytes()
                    pixels = pixels.get_data()
                    blank = pixels.count(0) == len(pixels)
                    self.osd.set_paintable(None if blank else texture)
                    self.osd_frame.set_visible(not blank)
            shown()

        shot = f"{remote.osd_shot_path(self.api)}&at={int(time.time() * 1000) % 2 ** 32}"
        image = remote.osd_image_path(self.api)
        if not image:
            self.get(shot, on_image, raw=True, quiet=True)
            return

        def on_shot(result):
            if result is None:
                shown()
                return
            self.get(f"{image}?{int(time.time() * 1000)}", on_image, raw=True, quiet=True)

        self.get(shot, on_shot, quiet=True)

    def confirm_power(self, state):
        if state is None:
            self.start_local()
            return
        try:
            standby = remote.standby_on(self.api, state)
        except (ValueError, AttributeError):
            self.show_status("Standby state not readable", True)
            return
        if standby:
            self.press("KEY_POWER")
            return
        dialog = Gtk.AlertDialog(message="Put the box into standby?", buttons=["Cancel", "Standby"],
                                 cancel_button=0, default_button=1)

        def answered(d, result):
            try:
                if d.choose_finish(result) == 1:
                    self.press("KEY_POWER")
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

        self.get(remote.standby_path(self.api), done, quiet=True)
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
            if not self.epg_timer:
                self.epg_timer = GLib.timeout_add_seconds(60, self.refresh_epg)
            self.grab_osd()
        elif self.get_mapped():
            # GTK keeps a size the compositor has once confirmed; shown anew, the window takes its default size
            self.set_visible(False)
            self.set_visible(True)

    def load_bouquets(self):
        self.retry_api(lambda _switched: self.fetch_bouquets())

    def fetch_bouquets(self):
        def done(text):
            if text is None:
                return
            try:
                bouquets = remote.parse_bouquets(self.api, text)
            except (ValueError, KeyError):
                self.show_status("Bouquet list not readable", True)
                return
            self.bouquet_numbers = [number for number, _, _ in bouquets]
            self.bouquet_web = [web for _, _, web in bouquets]
            self.bouquets.set_model(Gtk.StringList.new([name for _, name, _ in bouquets]))
            if bouquets:
                self.bouquets.set_selected(0)
                self.on_bouquet()

        self.get(remote.bouquets_path(self.api), done)

    def on_bouquet(self, *_):
        index = self.bouquets.get_selected()
        if index >= len(self.bouquet_numbers):
            return
        number = self.bouquet_numbers[index]
        web = self.bouquet_web[index]
        api = self.api

        def with_current(channels):
            def done(text):
                try:
                    current = remote.current_id(api, text)
                except ValueError:
                    current = ""
                self.fill_channels(channels, current)

            self.get(remote.current_path(api), done, quiet=True)

        if api == remote.CONTROL:
            def listed(text):
                if text is None:
                    return
                try:
                    channels = remote.parse_control_channels(text)
                except (ValueError, KeyError):
                    self.show_status("Channel list not readable", True)
                    return
                with_current(channels)

            self.get(remote.control_channels_path(number), listed)
            return

        def with_channels(channels):
            self.get_all(lambda cursor: remote.grid_path(number, cursor),
                         lambda grid: with_current(remote.build_channels(channels, grid or [], web)), quiet=True)

        self.get_all(lambda cursor: remote.channels_path(number, cursor),
                     lambda channels: channels is not None and with_channels(channels))

    def get_all(self, path_of, callback, quiet=False, items=None, cursor=None):
        """Every page of a list, handed on as one list; None when a page failed."""
        items = items if items is not None else []

        def done(text):
            if text is None:
                callback(None)
                return
            try:
                page, following = remote.parse_page(text)
            except (ValueError, AttributeError):
                if not quiet:
                    self.show_status("List not readable", True)
                callback(None)
                return
            items.extend(page)
            if following:
                self.get_all(path_of, callback, quiet, items, following)
            else:
                callback(items)

        self.get(path_of(cursor), done, quiet=quiet)

    def fill_channels(self, channels, current):
        rows = []
        child = self.channel_list.get_first_child()
        while child:
            rows.append(child)
            child = child.get_next_sibling()
        if [r.channel_id for r in rows] != [c["id"] for c in channels]:
            self.channel_list.remove_all()
            rows = [self.channel_row(c) for c in channels]
            for row in rows:
                self.channel_list.append(row)
        for row, channel in zip(rows, channels):
            (row.name_label.add_css_class if channel["id"] == current else row.name_label.remove_css_class)("current")
            now = channel["now"]
            row.epg_box.set_visible(now is not None)
            if now:
                row.epg_label.set_label(f"{now['start']}  {now['title']}")
                row.epg_bar.set_visible(now["percent"] >= 0)
                row.epg_bar.set_fraction(max(now["percent"], 0) / 100)
            row.set_tooltip_text(remote.epg_tooltip(channel))
            row.channel = channel
            row.record.set_visible(remote.record_request(self.api, channel) is not None)
            row.stream.set_visible(not remote.is_local(self.host))

    def channel_row(self, channel):
        row = Gtk.ListBoxRow()
        row.channel_id = channel["id"]
        box = Gtk.Box(spacing=8, margin_start=6, margin_end=6, margin_top=3, margin_bottom=3)
        num = Gtk.Label(label=channel["number"], width_chars=4, xalign=1, valign=Gtk.Align.START)
        num.add_css_class("number")
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        row.name_label = Gtk.Label(label=channel["name"], xalign=0, ellipsize=3)
        row.epg_label = Gtk.Label(xalign=0, ellipsize=3, hexpand=True)
        row.epg_label.add_css_class("epg")
        row.epg_bar = Gtk.ProgressBar(valign=Gtk.Align.CENTER, width_request=48)
        row.epg_bar.add_css_class("epg")
        row.epg_box = Gtk.Box(spacing=8)
        row.epg_box.append(row.epg_label)
        row.epg_box.append(row.epg_bar)
        text.append(row.name_label)
        text.append(row.epg_box)
        row.record = Gtk.Button(icon_name="media-record-symbolic", valign=Gtk.Align.CENTER)
        row.record.add_css_class("flat")
        row.record.set_tooltip_text("Record the programme that is on")
        row.record.connect("clicked", lambda *_: self.record(row.channel))
        row.stream = Gtk.Button(icon_name="media-playback-start-symbolic", valign=Gtk.Align.CENTER)
        row.stream.add_css_class("flat")
        row.stream.set_tooltip_text("Watch on this computer")
        row.stream.connect("clicked", lambda *_: self.stream(row.channel))
        box.append(num)
        box.append(text)
        box.append(row.record)
        box.append(row.stream)
        row.set_child(box)
        return row

    def record(self, channel):
        req = remote.record_request(self.api, channel)
        if not req:
            return
        title = channel["now"]["title"]
        self.send(req, lambda r: r is not None and self.show_status(f"Recording: {title}"))

    def stream(self, channel):
        def done(text):
            try:
                url = remote.stream_url(self.api, text).strip()
            except ValueError:
                url = ""
            if not url:
                self.show_status(f"{channel['name']}: no stream address", True)
                return
            if url.startswith("/"):
                url = urllib.parse.urljoin(self.base, url)
            command = remote.player_command(url)
            try:
                if command:
                    Gio.Subprocess.new(command, Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE)
                else:
                    Gio.AppInfo.launch_default_for_uri(url, None)
            except GLib.Error as err:
                self.show_status(f"Player: {err.message}", True)
                return
            self.show_status(f"Streaming {channel['name']}")

        self.get(remote.stream_path(self.api, channel["id"]), done)

    def refresh_epg(self):
        if not self.side.get_visible():
            self.epg_timer = 0
            return False
        self.retry_api(lambda switched: self.load_bouquets() if switched else self.on_bouquet())
        return True

    def retry_api(self, then):
        """A box first met on the control API is asked again for the REST API, which it
        may only have lacked while Neutrino was starting; then(True) once it answers."""
        if self.api != remote.CONTROL:
            then(False)
            return

        def probed(text):
            if text is None:
                then(False)
                return
            self.api = remote.API
            self.show_status(f"Connected to {self.host}")
            then(True)

        self.get(remote.PROBE_PATH, probed, quiet=True)

    def on_channel(self, _list, row):
        def done(result):
            if result is None:
                return
            self.show_status("Switched channel")
            self.follow_osd()
            child = self.channel_list.get_first_child()
            while child:
                (child.name_label.add_css_class if child is row else child.name_label.remove_css_class)("current")
                child = child.get_next_sibling()

        self.send(remote.zap_request(self.api, row.channel_id), done)


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
