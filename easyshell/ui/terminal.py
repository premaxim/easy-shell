"""Ein Terminal-Tab mit eingebettetem VTE, der einen ssh-Prozess ausführt."""

from __future__ import annotations

import os
from typing import Callable

import gi

gi.require_version("Vte", "3.91")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango, Vte  # noqa: E402

from . import theme  # noqa: E402

SSH_UNREACHABLE = 255  # ssh meldet Verbindungsfehler mit Exit-Code 255


class TerminalPage(Gtk.Box):
    def __init__(
        self,
        argv: list[str] | Callable[[], list[str]],
        app_theme: theme.Theme,
        font: str,
        target_label: str,
        on_reconnect: Callable[["TerminalPage"], None],
        success_text: str = "Verbindung beendet.",
        failure_text: str | None = None,
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        # Eine Funktion statt fester Liste: jeder (Neu-)Start bekommt z. B. einen frischen ControlMaster-Socket.
        self._argv = argv
        self.exited = False
        self._theme = app_theme
        self._on_reconnect = on_reconnect
        self._success_text = success_text
        self._failure_text = failure_text or (
            f"Keine Verbindung zu {target_label}. Prüfe, ob der Server läuft und SSH aktiviert ist."
        )

        self.banner = Adw.Banner(button_label="Neu verbinden")
        self.banner.connect("button-clicked", lambda *_: self._on_reconnect(self))
        self.append(self.banner)

        self.terminal = Vte.Terminal(
            hexpand=True, vexpand=True,
            scrollback_lines=10000,
            scroll_on_output=False, scroll_on_keystroke=True,
            css_classes=["pb-terminal"],
        )
        self.terminal.set_cursor_blink_mode(Vte.CursorBlinkMode.OFF)
        self.terminal.set_mouse_autohide(True)
        self.set_font(font)
        self.apply_colors()
        app_theme.on_change(self.apply_colors)
        self.terminal.connect("child-exited", self._child_exited)
        self._install_keys()
        if hasattr(self.terminal, "set_context_menu_model"):  # VTE ≥ 0.76
            menu = Gio.Menu()
            menu.append("Kopieren", "term.copy")
            menu.append("Einfügen", "term.paste")
            menu.append("Terminal-Schrift ändern…", "win.terminal-font")
            self.terminal.set_context_menu_model(menu)

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=self.terminal)
        self.append(scroller)
        self.spawn()

    # Prozess ------------------------------------------------------------

    def spawn(self) -> None:
        self.exited = False
        self.banner.set_revealed(False)
        self.terminal.reset(True, True)
        argv = self._argv() if callable(self._argv) else self._argv
        self.terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            os.path.expanduser("~"),
            argv,
            ["TERM=xterm-256color"],
            GLib.SpawnFlags.SEARCH_PATH,
            None, None,
            -1,
            None,
            self._spawned,
        )

    def _spawned(self, _terminal, _pid, error, *_):
        if error:
            self.exited = True
            self.banner.set_title(
                "ssh ließ sich nicht starten. Ist ein ssh-Client installiert? "
                f"({error.message if hasattr(error, 'message') else error})"
            )
            self.banner.add_css_class("pb-exit-error")
            self.banner.set_revealed(True)

    def _child_exited(self, _terminal, status: int) -> None:
        self.exited = True
        try:
            code = os.waitstatus_to_exitcode(status)  # VTE liefert den rohen wait-Status
        except ValueError:
            code = status
        if code == 0:
            self.banner.set_title(self._success_text)
            self.banner.remove_css_class("pb-exit-error")
        elif code == SSH_UNREACHABLE:
            self.banner.set_title(self._failure_text)
            self.banner.add_css_class("pb-exit-error")
        else:
            self.banner.set_title(f"Sitzung mit Code {code} beendet.")
            self.banner.remove_css_class("pb-exit-error")
        self.banner.set_revealed(True)

    def alive(self) -> bool:
        """Läuft der Prozess noch und ist der Tab offen?"""
        return not self.exited and self.get_root() is not None

    # Aussehen -----------------------------------------------------------

    def set_font(self, font: str) -> None:
        self.terminal.set_font(Pango.FontDescription.from_string(font))

    def apply_colors(self) -> None:
        dark = self._theme.dark
        t = theme.tokens(dark)
        self.terminal.set_colors(
            theme.rgba(t["text"]),
            theme.rgba(t["grund"]),
            [theme.rgba(c) for c in theme.TERMINAL_PALETTE[dark]],
        )
        self.terminal.set_color_cursor(theme.rgba(t["akzent"]))
        self.terminal.set_color_cursor_foreground(theme.rgba(t["grund"]))

    # Tasten -------------------------------------------------------------

    def _install_keys(self) -> None:
        group = Gio.SimpleActionGroup()
        for name, cb in (("copy", self.copy), ("paste", self.paste)):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", lambda *_a, cb=cb: cb())
            group.add_action(act)
        self.insert_action_group("term", group)

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._key_pressed)
        self.terminal.add_controller(keys)

    def _key_pressed(self, _ctl, keyval, _code, state) -> bool:
        mods = state & Gtk.accelerator_get_default_mod_mask()
        ctrl = Gdk.ModifierType.CONTROL_MASK
        shift = Gdk.ModifierType.SHIFT_MASK
        key = Gdk.keyval_to_lower(keyval)
        if mods == ctrl | shift and key == Gdk.KEY_c:
            self.copy()
            return True
        if mods == ctrl | shift and key == Gdk.KEY_v:
            self.paste()
            return True
        if mods & ctrl and keyval in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            self.terminal.set_font_scale(min(self.terminal.get_font_scale() + 0.1, 3))
            return True
        if mods & ctrl and keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            self.terminal.set_font_scale(max(self.terminal.get_font_scale() - 0.1, 0.5))
            return True
        if mods & ctrl and keyval in (Gdk.KEY_0, Gdk.KEY_KP_0):
            self.terminal.set_font_scale(1.0)
            return True
        return False

    def copy(self) -> None:
        self.terminal.copy_clipboard_format(Vte.Format.TEXT)

    def paste(self) -> None:
        self.terminal.paste_clipboard()
