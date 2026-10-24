"""Import, Schnellverbinden und Kürzel-Übersicht."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from gi.repository import Adw, Gtk

from ..models import Server
from ..ssh.config_parser import ImportCandidate, parse_ssh_config
from ..storage import ServerStore


class ImportDialog(Adw.Dialog):
    """Vorschau: was aus ~/.ssh/config übernommen wird."""

    def __init__(self, store: ServerStore, on_import: Callable[[list[Server]], None], path: Path | None = None):
        super().__init__(title="Aus ~/.ssh/config importieren", content_width=520, content_height=640)
        self._on_import = on_import
        self._checks: list[tuple[Gtk.CheckButton, ImportCandidate]] = []

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        page = Adw.PreferencesPage()
        toolbar.set_content(page)
        self.set_child(toolbar)

        candidates = parse_ssh_config(path)
        group = Adw.PreferencesGroup()
        page.add(group)
        if not candidates:
            group.set_description(
                "In ~/.ssh/config stehen keine Hosts ohne Platzhalter. "
                "Einträge wie „Host *“ gelten für alle Server und werden nicht übernommen."
            )
        else:
            group.set_description("Wähle aus, welche Hosts Patchbay übernehmen soll. Die Datei bleibt unverändert.")

        for cand in candidates:
            exists = store.contains_equivalent(cand.host, cand.port, cand.user) or store.find_by_name(cand.alias)
            details = [f"{cand.user}@{cand.host}" if cand.user else cand.host]
            if cand.port != 22:
                details[0] += f":{cand.port}"
            if cand.jump_host:
                details.append(f"über {cand.jump_host}")
            if cand.key_path:
                details.append(f"Key {Path(cand.key_path).name}")
            if exists:
                details.append("schon gespeichert")
            row = Adw.ActionRow(title=cand.alias, subtitle=", ".join(details), title_lines=1)
            check = Gtk.CheckButton(active=not exists, sensitive=not exists, valign=Gtk.Align.CENTER)
            check.connect("toggled", lambda *_: self._update())
            row.add_prefix(check)
            row.set_activatable_widget(check)
            group.add(row)
            self._checks.append((check, cand))

        bar = Gtk.Box(margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self._button = Gtk.Button(hexpand=True, css_classes=["suggested-action"])
        self._button.connect("clicked", self._import)
        bar.append(self._button)
        toolbar.add_bottom_bar(bar)
        self._update()

    def _selected(self) -> list[ImportCandidate]:
        return [c for check, c in self._checks if check.get_active() and check.get_sensitive()]

    def _update(self) -> None:
        n = len(self._selected())
        self._button.set_label("1 Server importieren" if n == 1 else f"{n} Server importieren")
        self._button.set_sensitive(n > 0)

    def _import(self, *_):
        servers = [
            Server(name=c.alias, host=c.host, port=c.port, user=c.user,
                   key_path=c.key_path, jump_host=c.jump_host, color="grey")
            for c in self._selected()
        ]
        self._on_import(servers)
        self.close()


def quick_connect_dialog(on_connect: Callable[[str], None]) -> Adw.AlertDialog:
    dialog = Adw.AlertDialog(
        heading="Schnell verbinden",
        body="Gib user@host:port ein oder den Namen eines gespeicherten Servers.",
    )
    entry = Gtk.Entry(placeholder_text="max@192.168.1.20", activates_default=True)
    dialog.set_extra_child(entry)
    dialog.add_response("cancel", "Abbrechen")
    dialog.add_response("connect", "Verbinden")
    dialog.set_response_appearance("connect", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("connect")
    dialog.set_close_response("cancel")
    dialog.set_response_enabled("connect", False)
    entry.connect("changed", lambda e: dialog.set_response_enabled("connect", bool(e.get_text().strip())))

    def response(_d, rid):
        if rid == "connect":
            on_connect(entry.get_text())

    dialog.connect("response", response)
    dialog.set_focus(entry)
    return dialog


SHORTCUTS = [
    ("Server", [
        ("<Control>n", "Neuer Server"),
        ("<Control>f", "Server suchen (oder einfach lostippen)"),
        ("Return", "Gewählten Server verbinden"),
    ]),
    ("Sessions", [
        ("<Control>t", "Schnell verbinden"),
        ("<Control>w", "Tab schließen"),
        ("<Control>Page_Up", "Vorheriger Tab"),
        ("<Control>Page_Down", "Nächster Tab"),
    ]),
    ("Im Terminal", [
        ("<Control><Shift>n <Control><Shift>t <Control><Shift>w", "Wie oben – Strg+N/T/W/F gehören dort der Shell"),
        ("<Control><Shift>c", "Kopieren"),
        ("<Control><Shift>v", "Einfügen"),
        ("<Control>plus <Control>minus <Control>0", "Schrift größer, kleiner, zurücksetzen"),
    ]),
    ("Allgemein", [
        ("<Control>question", "Diese Übersicht"),
    ]),
]


def shortcuts_dialog() -> Adw.Dialog:
    dialog = Adw.Dialog(title="Tastenkürzel", content_width=560, content_height=640)
    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())
    page = Adw.PreferencesPage()
    for title, items in SHORTCUTS:
        group = Adw.PreferencesGroup(title=title)
        for accel, label in items:
            row = Adw.ActionRow(title=label)
            row.add_suffix(Gtk.ShortcutLabel(accelerator=accel, valign=Gtk.Align.CENTER))
            group.add(row)
        page.add(group)
    toolbar.set_content(page)
    dialog.set_child(toolbar)
    return dialog
