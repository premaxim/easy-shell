"""Kleine wiederverwendbare Bausteine: LED, Kabelstreifen, Server-Zeile."""

from __future__ import annotations

import math

from gi.repository import Gio, GLib, Gtk, Pango

from ..models import CABLE_COLORS, Server
from ..ssh.status import LABELS, Status
from . import theme


class Led(Gtk.DrawingArea):
    """Status-LED. Form codiert den Zustand zusätzlich zur Farbe:
    gefüllt = erreichbar, Ring = nicht erreichbar, halb = prüfe."""

    SIZE = 12

    def __init__(self, app_theme: theme.Theme):
        super().__init__(content_width=self.SIZE, content_height=self.SIZE, valign=Gtk.Align.CENTER)
        self._theme = app_theme
        self.status = Status.CHECKING
        self.set_draw_func(self._draw)

    def set_status(self, status: Status) -> None:
        self.status = status
        self.queue_draw()

    def _draw(self, _area, cr, width, height):
        t = theme.tokens(self._theme.dark)
        key = {"online": "online", "offline": "offline", "checking": "pruefen"}[self.status.value]
        color = theme.rgba(t[key])
        cx, cy, r = width / 2, height / 2, min(width, height) / 2 - 1
        cr.set_source_rgba(color.red, color.green, color.blue, 1)
        if self.status is Status.ONLINE:
            cr.arc(cx, cy, r, 0, 2 * math.pi)
            cr.fill()
        elif self.status is Status.OFFLINE:
            cr.set_line_width(2)
            cr.arc(cx, cy, r - 1, 0, 2 * math.pi)
            cr.stroke()
        else:
            cr.set_line_width(1.5)
            cr.arc(cx, cy, r - 0.75, 0, 2 * math.pi)
            cr.stroke()
            cr.arc(cx, cy, r, math.pi / 2, 3 * math.pi / 2)  # linke Hälfte gefüllt
            cr.fill()


def stripe(color: str) -> Gtk.Box:
    box = Gtk.Box(css_classes=["pb-stripe", f"cable-{color}"])
    return box


def stripe_icon(color: str) -> Gio.Icon:
    """Kabelstreifen als Tab-Icon."""
    hex_ = CABLE_COLORS.get(color, CABLE_COLORS["blue"])[1]
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
        f'<rect x="6" y="1" width="4" height="14" rx="2" fill="{hex_}"/></svg>'
    )
    return Gio.BytesIcon.new(GLib.Bytes.new(svg.encode()))


def server_menu(server: Server) -> Gio.Menu:
    target = GLib.Variant.new_string(server.id)

    def item(label, action):
        mi = Gio.MenuItem.new(label, None)
        mi.set_action_and_target_value(f"win.{action}", target)
        return mi

    menu = Gio.Menu()
    main = Gio.Menu()
    main.append_item(item("Verbinden", "server-connect"))
    main.append_item(item("Bearbeiten", "server-edit"))
    main.append_item(item("Duplizieren", "server-duplicate"))
    menu.append_section(None, main)
    tools = Gio.Menu()
    tools.append_item(item("Befehl kopieren", "server-copy-command"))
    tools.append_item(item("Key auf Server kopieren", "server-copy-id"))
    menu.append_section(None, tools)
    danger = Gio.Menu()
    danger.append_item(item("Löschen", "server-delete"))
    menu.append_section(None, danger)
    return menu


class ServerRow(Gtk.ListBoxRow):
    def __init__(self, server: Server, app_theme: theme.Theme, with_menu: bool = True):
        super().__init__()
        self.server = server
        box = Gtk.Box(spacing=12)
        self.set_child(box)

        self._stripe = stripe(server.color)
        box.append(self._stripe)

        self.led = Led(app_theme)
        box.append(self.led)

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True, spacing=2)
        self._name = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, css_classes=["pb-name"])
        self._address = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, css_classes=["pb-address"])
        labels.append(self._name)
        labels.append(self._address)
        box.append(labels)

        self._menu_button = None
        if with_menu:
            self._menu_button = Gtk.MenuButton(
                icon_name="view-more-symbolic",
                valign=Gtk.Align.CENTER,
                margin_end=6,
                css_classes=["flat", "pb-row-menu"],
                tooltip_text="Aktionen",
            )
            box.append(self._menu_button)
            # Rechtsklick und langes Drücken (Touch/Deck) öffnen dasselbe Menü.
            click = Gtk.GestureClick(button=3)
            click.connect("pressed", lambda *_: self._menu_button.popup())
            self.add_controller(click)
            press = Gtk.GestureLongPress()
            press.connect("pressed", lambda *_: self._menu_button.popup())
            self.add_controller(press)
        else:
            box.set_margin_end(16)
        self.update(server)

    def update(self, server: Server) -> None:
        self.server = server
        self._name.set_label(server.name)
        self._address.set_label(server.address)
        for key in CABLE_COLORS:
            self._stripe.remove_css_class(f"cable-{key}")
        self._stripe.add_css_class(f"cable-{server.color}")
        if self._menu_button:
            self._menu_button.set_menu_model(server_menu(server))
        self.set_status(self.led.status)

    def set_status(self, status: Status) -> None:
        self.led.set_status(status)
        text = f"{self.server.name}, {LABELS[status]}"
        if self.server.jump_host and status is not Status.CHECKING:
            text += " (Jump-Host geprüft)"
        self.set_tooltip_text(text)
        self.update_property([Gtk.AccessibleProperty.LABEL], [f"{text}, {self.server.address}"])


def group_header(title: str) -> Gtk.Widget:
    box = Gtk.Box(spacing=8, css_classes=["pb-group-header"])
    box.append(Gtk.Label(label=title, xalign=0))
    box.append(Gtk.Separator(hexpand=True, valign=Gtk.Align.CENTER))
    return box
