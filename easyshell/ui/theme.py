"""Design-Tokens, CSS und Terminal-Palette. Folgt dem Systemtheme (hell/dunkel)."""

from __future__ import annotations

from gi.repository import Adw, Gdk, Gtk

from ..models import CABLE_COLORS

DARK = {
    "grund": "#14202B",
    "flaeche": "#1B2B39",
    "flaeche-hover": "#213447",
    "flaeche-aktiv": "#26405A",
    "linie": "#2C4152",
    "text": "#E4ECF1",
    "text-leise": "#8DA2B2",
    "online": "#5DB98C",
    "offline": "#CC6470",
    "pruefen": "#D9B95B",
    "akzent": "#4A8BD4",
    "akzent-text": "#7FB0E6",
}

LIGHT = {
    "grund": "#EEF3F6",
    "flaeche": "#F8FAFB",
    "flaeche-hover": "#E6EEF3",
    "flaeche-aktiv": "#D8E5EE",
    "linie": "#C8D5DE",
    "text": "#14202B",
    "text-leise": "#4D6475",
    "online": "#2E8A5F",
    "offline": "#B3434F",
    "pruefen": "#9C7A1E",
    "akzent": "#2F6DB5",
    "akzent-text": "#245A99",
}

TERMINAL_PALETTE = {
    True: [  # dunkel
        "#1B2B39", "#CC6470", "#5DB98C", "#D9B95B", "#4A8BD4", "#9B7FD1", "#4FB3BF", "#C9D6DF",
        "#4E6576", "#E0808B", "#7FD1A8", "#E8CF80", "#78A9E3", "#B7A0E3", "#7CCAD3", "#F3F7F9",
    ],
    False: [  # hell
        "#14202B", "#B3434F", "#2E8A5F", "#8A6A12", "#2F6DB5", "#7559B3", "#237F8A", "#8DA2B2",
        "#4D6475", "#C4535F", "#36A16F", "#A8841F", "#3E7FC9", "#8A6CC7", "#2C97A3", "#C8D5DE",
    ],
}


def tokens(dark: bool) -> dict[str, str]:
    return DARK if dark else LIGHT


def rgba(hex_color: str) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.parse(hex_color)
    return color


def _adw_colors(t: dict[str, str]) -> dict[str, str]:
    """Abbildung unserer Tokens auf libadwaitas Farbnamen."""
    return {
        "window-bg-color": t["grund"],
        "window-fg-color": t["text"],
        "view-bg-color": t["grund"],
        "view-fg-color": t["text"],
        "headerbar-bg-color": t["grund"],
        "headerbar-fg-color": t["text"],
        "headerbar-backdrop-color": t["grund"],
        "headerbar-border-color": t["linie"],
        "headerbar-shade-color": t["linie"],
        "sidebar-bg-color": t["flaeche"],
        "sidebar-fg-color": t["text"],
        "sidebar-backdrop-color": t["flaeche"],
        "sidebar-border-color": t["linie"],
        "sidebar-shade-color": t["linie"],
        "card-bg-color": t["flaeche"],
        "card-fg-color": t["text"],
        "dialog-bg-color": t["flaeche"],
        "dialog-fg-color": t["text"],
        "popover-bg-color": t["flaeche"],
        "popover-fg-color": t["text"],
        "accent-bg-color": t["akzent"],
        "accent-fg-color": "#FFFFFF",
        "accent-color": t["akzent-text"],
        "destructive-bg-color": t["offline"],
        "destructive-fg-color": "#FFFFFF",
        "destructive-color": t["offline"],
        "border-color": t["linie"],
    }


def colors_css(dark: bool) -> str:
    t = tokens(dark)
    mapping = _adw_colors(t)
    lines = []
    # Ältere libadwaita (< 1.6) nutzt @define-color, neuere CSS-Variablen.
    for name, value in mapping.items():
        lines.append(f"@define-color {name.replace('-', '_')} {value};")
    if Adw.get_minor_version() >= 6:
        lines.append(":root {")
        lines += [f"  --{name}: {value};" for name, value in mapping.items()]
        lines.append("}")
    for key, value in t.items():
        lines.append(f"@define-color pb_{key.replace('-', '_')} {value};")
    return "\n".join(lines)


BASE_CSS = """
window, dialog, popover {
  font-family: "Atkinson Hyperlegible Next", "Atkinson Hyperlegible", sans-serif;
  font-size: 15px;
}

/* Server-Liste: Zeilen, keine Karten */
list.pb-ports { background: transparent; }
list.pb-ports > row {
  min-height: 56px;
  padding: 0;
  border-radius: 0;
  transition: background-color 150ms ease-out;
}
list.pb-ports > row:hover { background-color: @pb_flaeche_hover; }
list.pb-ports > row:selected,
list.pb-ports > row:active { background-color: @pb_flaeche_aktiv; }
list.pb-ports > row:focus-visible {
  outline: 2px solid @pb_akzent;
  outline-offset: -2px;
}

.pb-stripe {
  min-width: 4px;
  margin: 10px 0;
  border-radius: 0 2px 2px 0;
}
""" + "".join(
    f".cable-{key} {{ background-color: {hex_}; }}\n" for key, (_, hex_) in CABLE_COLORS.items()
) + """
.pb-name { font-weight: 600; }
.pb-address, .pb-quiet { color: @pb_text_leise; font-size: 13px; font-feature-settings: "tnum"; }

.pb-group-header { padding: 16px 16px 4px 16px; }
.pb-group-header label { color: @pb_text_leise; font-size: 13px; font-weight: 600; }
.pb-group-header separator { background-color: @pb_linie; min-height: 1px; }

.pb-sidebar-bar { min-height: 47px; padding: 0 6px 0 10px; }
.pb-search { min-height: 36px; margin: 6px 0; }
.pb-sidebar-footer { padding: 8px 12px 12px 12px; border-top: 1px solid @pb_linie; }

button { min-height: 40px; border-radius: 6px; }
button.pb-row-menu { min-width: 44px; min-height: 44px; border-radius: 6px; }
button.pb-add-server { font-weight: 600; }
button:focus-visible { outline: 2px solid @pb_akzent; outline-offset: 2px; }

/* Kabelfarben-Auswahl im Editor */
.pb-swatch {
  min-width: 44px; min-height: 44px;
  padding: 0;
  border-radius: 22px;
  background: transparent;
  box-shadow: none;
}
.pb-swatch .pb-dot { min-width: 26px; min-height: 26px; border-radius: 13px; }
.pb-swatch:checked { box-shadow: inset 0 0 0 2px @pb_text; }
.pb-swatch:focus-visible { outline: 2px solid @pb_akzent; outline-offset: 0; }

.pb-notes {
  border: 1px solid @pb_linie;
  border-radius: 6px;
  padding: 8px;
  background-color: @pb_grund;
}
.pb-notes text { background: transparent; }

/* Startfläche */
.pb-title { font-size: 20px; font-weight: 600; }
.pb-section-label { color: @pb_text_leise; font-size: 13px; font-weight: 600; }
.pb-welcome list.pb-ports { border-top: 1px solid @pb_linie; border-bottom: 1px solid @pb_linie; }

/* Terminal-Seite */
.pb-terminal { padding: 6px 0 0 8px; }
banner.pb-exit-error > revealer > widget { background-color: alpha(@pb_offline, 0.18); }
"""


class Theme:
    """Hält die CSS-Provider aktuell, wenn das System zwischen hell und dunkel wechselt."""

    def __init__(self):
        self.style = Adw.StyleManager.get_default()
        # Folgt dem Systemtheme; ohne Angabe wäre „hell bevorzugt“ der Standard.
        self.style.set_color_scheme(Adw.ColorScheme.DEFAULT)
        display = Gdk.Display.get_default()
        self._base = Gtk.CssProvider()
        self._load(self._base, BASE_CSS)
        self._colors = Gtk.CssProvider()
        prio = Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        Gtk.StyleContext.add_provider_for_display(display, self._colors, prio)
        Gtk.StyleContext.add_provider_for_display(display, self._base, prio + 1)
        self._listeners = []
        self.style.connect("notify::dark", lambda *_: self._apply())
        self._apply()

    @staticmethod
    def _load(provider: Gtk.CssProvider, css: str) -> None:
        if hasattr(provider, "load_from_string"):  # GTK ≥ 4.12
            provider.load_from_string(css)
        else:
            provider.load_from_data(css, -1)

    @property
    def dark(self) -> bool:
        return self.style.get_dark()

    def on_change(self, callback) -> None:
        self._listeners.append(callback)

    def off(self, callback) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _apply(self) -> None:
        self._load(self._colors, colors_css(self.dark))
        for callback in self._listeners:
            callback()
