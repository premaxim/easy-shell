"""Server anlegen und bearbeiten – als Adw.Dialog (auf schmalen Fenstern ein Bottom-Sheet)."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Callable

from gi.repository import Adw, Gio, GLib, Gtk

from ..models import CABLE_COLORS, DEFAULT_COLOR, Server
from ..storage import ServerStore


class ServerEditor(Adw.Dialog):
    def __init__(self, store: ServerStore, server: Server | None, on_save: Callable[[Server], None]):
        self._new = server is None
        super().__init__(
            title="Neuer Server" if self._new else "Server bearbeiten",
            content_width=520,
            content_height=720,
        )
        self._store = store
        self._server = server or Server(name="", host="")
        self._on_save = on_save
        self._color_touched = not self._new
        self._key_path = self._server.key_path

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        page = Adw.PreferencesPage()
        toolbar.set_content(page)
        self.set_child(toolbar)

        # Verbindung
        conn = Adw.PreferencesGroup(title="Verbindung")
        self.name_row = Adw.EntryRow(title="Name", text=self._server.name)
        self.host_row = Adw.EntryRow(title="Host oder IP-Adresse", text=self._server.host)
        self.port_row = Adw.SpinRow.new_with_range(1, 65535, 1)
        self.port_row.set_title("Port")
        self.port_row.set_value(self._server.port)
        self.user_row = Adw.EntryRow(title="Benutzer", text=self._server.user)
        for row in (self.name_row, self.host_row, self.port_row, self.user_row):
            conn.add(row)
        page.add(conn)

        # Anmeldung
        auth = Adw.PreferencesGroup(
            title="Anmeldung",
            description="easyShell speichert keine Passwörter. Fragt der Server danach, "
            "erscheint die Abfrage im Terminal.",
        )
        self.key_row = Adw.ActionRow(title="SSH-Key")
        self._clear_key = Gtk.Button(
            icon_name="edit-clear-symbolic", valign=Gtk.Align.CENTER,
            css_classes=["flat"], tooltip_text="Key entfernen",
        )
        self._clear_key.connect("clicked", lambda *_: self._set_key(""))
        choose = Gtk.Button(label="Key wählen", valign=Gtk.Align.CENTER)
        choose.connect("clicked", self._choose_key)
        self.key_row.add_suffix(self._clear_key)
        self.key_row.add_suffix(choose)
        auth.add(self.key_row)
        self.jump_row = Adw.EntryRow(title="Jump-Host (optional)", text=self._server.jump_host)
        self.jump_row.set_tooltip_text("user@host:port oder der Name eines gespeicherten Servers")
        auth.add(self.jump_row)
        page.add(auth)
        self._set_key(self._key_path)

        # Ordnung
        order = Adw.PreferencesGroup(title="Gruppe und Kabelfarbe")
        self.group_row = Adw.EntryRow(title="Gruppe", text=self._server.group)
        groups = store.groups()
        if groups:
            menu = Gio.Menu()
            for g in groups:
                item = Gio.MenuItem.new(g, None)
                item.set_action_and_target_value("editor.group", GLib.Variant.new_string(g))
                menu.append_item(item)
            pick = Gtk.MenuButton(
                icon_name="pan-down-symbolic", menu_model=menu, valign=Gtk.Align.CENTER,
                css_classes=["flat"], tooltip_text="Vorhandene Gruppe wählen",
            )
            self.group_row.add_suffix(pick)
            actions = Gio.SimpleActionGroup()
            act = Gio.SimpleAction.new("group", GLib.VariantType.new("s"))
            act.connect("activate", lambda _a, v: self.group_row.set_text(v.get_string()))
            actions.add_action(act)
            self.insert_action_group("editor", actions)
        self.group_row.connect("changed", self._group_changed)
        order.add(self.group_row)

        swatches = Gtk.Box(spacing=4, margin_top=12, halign=Gtk.Align.START)
        self._swatches: dict[str, Gtk.ToggleButton] = {}
        first = None
        for key, (label, _hex) in CABLE_COLORS.items():
            btn = Gtk.ToggleButton(css_classes=["pb-swatch"], tooltip_text=label)
            btn.set_child(Gtk.Box(css_classes=["pb-dot", f"cable-{key}"], halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER))
            btn.update_property([Gtk.AccessibleProperty.LABEL], [f"Kabelfarbe {label}"])
            if first:
                btn.set_group(first)
            else:
                first = btn
            btn.connect("toggled", self._swatch_toggled)
            swatches.append(btn)
            self._swatches[key] = btn
        self._swatches.get(self._server.color, self._swatches[DEFAULT_COLOR]).set_active(True)
        self._color_touched = not self._new  # set_active oben zählt nicht als Nutzerwahl
        order.add(swatches)
        page.add(order)

        # Notizen
        notes_group = Adw.PreferencesGroup(title="Notizen")
        self.notes = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, accepts_tab=False, css_classes=["pb-notes"])
        self.notes.set_size_request(-1, 96)
        self.notes.get_buffer().set_text(self._server.notes)
        notes_group.add(self.notes)
        page.add(notes_group)

        # Fußleiste
        bar = Gtk.Box(margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.save_button = Gtk.Button(label="Server speichern", hexpand=True, css_classes=["suggested-action"])
        self.save_button.connect("clicked", self._save)
        bar.append(self.save_button)
        toolbar.add_bottom_bar(bar)
        self.set_default_widget(self.save_button)

        for row in (self.name_row, self.host_row):
            row.connect("changed", lambda *_: self._validate())
            row.connect("entry-activated", lambda *_: self._save() if self.save_button.get_sensitive() else None)
        self._validate()
        self.set_focus(self.name_row)

    # Hilfen -------------------------------------------------------------

    def _selected_color(self) -> str:
        return next((k for k, b in self._swatches.items() if b.get_active()), DEFAULT_COLOR)

    def _swatch_toggled(self, btn: Gtk.ToggleButton) -> None:
        if btn.get_active():
            self._color_touched = True

    def _group_changed(self, row: Adw.EntryRow) -> None:
        if self._color_touched:
            return
        color = self._store.color_for_group(row.get_text().strip())
        if color:
            self._swatches[color].set_active(True)
            self._color_touched = False

    def _set_key(self, path: str) -> None:
        self._key_path = path
        if path:
            self.key_row.set_subtitle(path.replace(str(Path.home()), "~", 1))
        else:
            self.key_row.set_subtitle("Keiner gewählt – ssh-agent und Standard-Keys werden genutzt")
        self._clear_key.set_visible(bool(path))

    def _choose_key(self, *_):
        dialog = Gtk.FileDialog(title="SSH-Key wählen", modal=True)
        ssh_dir = Path.home() / ".ssh"
        if ssh_dir.is_dir():
            dialog.set_initial_folder(Gio.File.new_for_path(str(ssh_dir)))

        def done(dlg, result):
            try:
                file = dlg.open_finish(result)
            except GLib.Error:
                return  # abgebrochen
            path = file.get_path()
            if path and path.endswith(".pub"):
                path = path[:-4]  # ssh -i erwartet den privaten Key
            if path:
                self._set_key(path)

        dialog.open(self.get_root(), None, done)

    def _validate(self) -> None:
        name = self.name_row.get_text().strip()
        host = self.host_row.get_text().strip()
        host_ok = bool(host) and " " not in host
        if host and not host_ok:
            self.host_row.add_css_class("error")
            self.host_row.set_tooltip_text("Der Host darf keine Leerzeichen enthalten.")
        else:
            self.host_row.remove_css_class("error")
            self.host_row.set_tooltip_text(None)
        self.save_button.set_sensitive(bool(name) and host_ok)

    def _save(self, *_):
        buf = self.notes.get_buffer()
        server = replace(
            self._server,
            name=self.name_row.get_text().strip(),
            host=self.host_row.get_text().strip(),
            port=int(self.port_row.get_value()),
            user=self.user_row.get_text().strip(),
            key_path=os.path.expanduser(self._key_path) if self._key_path else "",
            jump_host=self.jump_row.get_text().strip(),
            group=self.group_row.get_text().strip(),
            color=self._selected_color(),
            notes=buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False),
        )
        self._on_save(server)
        self.close()
