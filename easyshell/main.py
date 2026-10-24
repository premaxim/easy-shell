"""Einstiegspunkt."""

from __future__ import annotations

import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Vte", "3.91")
from gi.repository import Adw, Gio, GLib  # noqa: E402

from . import APP_ID  # noqa: E402
from .storage import ServerStore  # noqa: E402


class EasyShellApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        GLib.set_application_name("easyShell")
        self.store = ServerStore()
        self.theme = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        from .ui.theme import Theme
        self.theme = Theme()
        self.store.load()
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])

    def do_activate(self):
        window = self.get_active_window()
        if not window:
            from .ui.window import EasyShellWindow
            window = EasyShellWindow(self, self.store, self.theme)
            if os.environ.get("EASYSHELL_SCREENSHOT"):
                from .devtools import schedule_screenshot
                schedule_screenshot(window, os.environ["EASYSHELL_SCREENSHOT"])
        window.present()


def main() -> int:
    return EasyShellApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
