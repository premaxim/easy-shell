"""Nur für die Entwicklung: Fenster als PNG rendern (EASYSHELL_SCREENSHOT=pfad.png).

Optional: EASYSHELL_SCREENSHOT_SCRIPT = durch Kommas getrennte Schritte,
z. B. ``connect:NAS,editor,import,search:pi,shortcuts``.
"""

from __future__ import annotations

import os

from gi.repository import GLib, Gtk


def _render(window: Gtk.Window, path: str) -> None:
    paintable = Gtk.WidgetPaintable.new(window)
    width, height = window.get_width(), window.get_height()
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, width, height)
    node = snapshot.to_node()
    texture = window.get_renderer().render_texture(node, None)
    texture.save_to_png(path)
    print(f"Screenshot: {path}")


def _scroll_dialog_down(window) -> bool:
    def walk(widget):
        child = widget.get_first_child()
        while child:
            yield child
            yield from walk(child)
            child = child.get_next_sibling()

    dialog = window.get_visible_dialog()
    for widget in walk(dialog) if dialog else ():
        if isinstance(widget, Gtk.ScrolledWindow):
            adj = widget.get_vadjustment()
            adj.set_value(adj.get_upper())
    return GLib.SOURCE_REMOVE


def _type_into_terminal(window, text: str) -> bool:
    if text.startswith("@"):  # @datei: Text aus Datei lesen (z. B. ein Test-Passwort)
        with open(text[1:], encoding="utf-8") as fh:
            text = fh.read().strip()
    page = window.tabview.get_selected_page()
    if page:
        page.get_child().terminal.feed_child((text + "\r").encode())
    return GLib.SOURCE_REMOVE


def schedule_screenshot(window, path: str) -> None:
    size = os.environ.get("EASYSHELL_SIZE")
    if size:
        w, _, h = size.partition("x")
        window.set_default_size(int(w), int(h))
    steps = [s for s in os.environ.get("EASYSHELL_SCREENSHOT_SCRIPT", "").split(",") if s]

    def run_steps():
        for step in steps:
            name, _, arg = step.partition(":")
            if name == "connect":
                server = window.store.find_by_name(arg)
                if server:
                    window.connect_server(server)
            elif name == "editor":
                window.edit_server(window.store.find_by_name(arg) if arg else None)
            elif name == "import":
                window.activate_action("win.import", None)
            elif name == "shortcuts":
                window.activate_action("win.shortcuts", None)
            elif name == "quick":
                window.activate_action("win.quick-connect", None)
            elif name == "search":
                window.search.set_text(arg)
            elif name == "type":  # type:<verzögerung ms>:<text> – tippt ins aktive Terminal, mit Enter
                delay, _, text = arg.partition(":")
                GLib.timeout_add(int(delay), _type_into_terminal, window, text)
            elif name == "scrolldown":
                GLib.timeout_add(700, _scroll_dialog_down, window)
        return GLib.SOURCE_REMOVE

    def shoot():
        _render(window, path)
        window.get_application().quit()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(600, run_steps)
    GLib.timeout_add(int(os.environ.get("EASYSHELL_SCREENSHOT_DELAY", "2500")), shoot)
