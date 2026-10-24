"""Hauptfenster: Server-Liste links, Terminal-Tabs rechts."""

from __future__ import annotations

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

from ..models import Server
from ..ssh import connection
from ..ssh.status import Status, StatusMonitor
from ..storage import ServerStore
from . import theme
from .dialogs import ImportDialog, quick_connect_dialog, shortcuts_dialog
from .editor import ServerEditor
from .terminal import TerminalPage
from .widgets import ServerRow, group_header, stripe_icon


class PatchbayWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, store: ServerStore, app_theme: theme.Theme):
        super().__init__(application=app, title="Patchbay", default_width=1180, default_height=760)
        self.set_size_request(360, 360)
        self.store = store
        self.theme = app_theme
        self._rows: dict[str, ServerRow] = {}
        self._welcome_rows: list[ServerRow] = []
        self._query = ""

        self.toasts = Adw.ToastOverlay()
        self.split = Adw.OverlaySplitView(min_sidebar_width=260, max_sidebar_width=320, sidebar_width_fraction=0.26)
        self.toasts.set_child(self.split)
        self.set_content(self.toasts)

        self.split.set_sidebar(self._build_sidebar())
        self.split.set_content(self._build_content())

        # Schmale Fenster (Deck hochkant, halbe Bildschirmbreite): Seitenleiste einklappen.
        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 720sp"))
        bp.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(bp)
        self.split.connect("notify::collapsed", lambda *_: self._sync_sidebar_button())

        self._install_actions()
        self._install_shortcuts()

        self.status = StatusMonitor(self._status_changed, store.find_by_name)
        self.rebuild_list()
        self.status.start(lambda: list(self.store.servers))
        self.connect("close-request", self._on_close)
        self._update_content()

        if store.load_warning:
            self.toast(store.load_warning, timeout=0)

    # Aufbau -------------------------------------------------------------

    def _build_sidebar(self) -> Gtk.Widget:
        view = Adw.ToolbarView()
        # Kein App-Titel in der Seitenleiste (steht im Fenstertitel) – die Suche nimmt seinen Platz ein.
        self.search = Gtk.SearchEntry(placeholder_text="Server suchen", hexpand=True, css_classes=["pb-search"])
        self.search.connect("search-changed", self._search_changed)
        self.search.connect("activate", self._search_activate)
        self.search.connect("stop-search", lambda *_: self.search.set_text(""))
        bar = Gtk.Box(spacing=6, css_classes=["pb-sidebar-bar"])
        bar.append(Gtk.WindowControls(side=Gtk.PackType.START))  # nur sichtbar, wenn Knöpfe links liegen
        bar.append(self.search)
        menu = Gio.Menu()
        menu.append("Aus ~/.ssh/config importieren", "win.import")
        menu.append("Terminal-Schrift ändern…", "win.terminal-font")
        menu.append("Tastenkürzel", "win.shortcuts")
        menu.append("Über Patchbay", "win.about")
        bar.append(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, tooltip_text="Hauptmenü",
                                  valign=Gtk.Align.CENTER, css_classes=["flat"]))
        view.add_top_bar(Gtk.WindowHandle(child=bar))

        self.listbox = Gtk.ListBox(css_classes=["pb-ports"], selection_mode=Gtk.SelectionMode.SINGLE)
        self.listbox.set_filter_func(self._filter)
        self.listbox.set_header_func(self._header)
        self.listbox.connect("row-activated", lambda _lb, row: self.connect_server(row.server))
        self._placeholder = Gtk.Label(wrap=True, margin_top=24, margin_start=16, margin_end=16,
                                      css_classes=["pb-quiet"], justify=Gtk.Justification.CENTER)
        self.listbox.set_placeholder(self._placeholder)
        view.set_content(Gtk.ScrolledWindow(child=self.listbox, hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True))

        footer = Gtk.Box(css_classes=["pb-sidebar-footer"])
        add = Gtk.Button(hexpand=True, css_classes=["flat", "pb-add-server"], action_name="win.new-server",
                         tooltip_text="Neuer Server (Strg+N)")
        add.set_child(Adw.ButtonContent(icon_name="list-add-symbolic", label="Server hinzufügen"))
        footer.append(add)
        view.add_bottom_bar(footer)
        self.sidebar_view = view
        return view

    def _build_content(self) -> Gtk.Widget:
        view = Adw.ToolbarView(top_bar_style=Adw.ToolbarStyle.FLAT)
        header = Adw.HeaderBar()
        self.sidebar_button = Gtk.ToggleButton(icon_name="sidebar-show-symbolic", tooltip_text="Serverliste zeigen")
        self.split.bind_property("show-sidebar", self.sidebar_button, "active",
                                          GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
        header.pack_start(self.sidebar_button)

        self.tabview = Adw.TabView()
        self.tabview.connect("notify::n-pages", lambda *_: self._update_content())
        self.tabview.connect("close-page", self._close_page)
        self.tabview.connect("notify::selected-page", lambda *_: self._focus_terminal())
        tab_menu = Gio.Menu()
        tab_menu.append("Neu verbinden", "win.tab-reconnect")
        tab_menu.append("Terminal-Schrift ändern…", "win.terminal-font")
        tab_menu.append("Tab schließen", "win.close-tab")
        self.tabview.set_menu_model(tab_menu)

        self.tabbar = Adw.TabBar(view=self.tabview, autohide=False, hexpand=True)
        plus = Gtk.Button(icon_name="list-add-symbolic", action_name="win.quick-connect",
                          tooltip_text="Schnell verbinden (Strg+T)", css_classes=["flat"])
        self.tabbar.set_end_action_widget(plus)
        header.set_title_widget(self.tabbar)
        view.add_top_bar(header)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=150)
        self.welcome = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.stack.add_named(self.welcome, "welcome")
        self.stack.add_named(self.tabview, "tabs")
        view.set_content(self.stack)
        return view

    def _build_welcome(self) -> Gtk.Widget:
        clamp = Adw.Clamp(maximum_size=560, margin_top=56, margin_bottom=32, margin_start=16, margin_end=16)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["pb-welcome"])
        clamp.set_child(box)
        has_servers = bool(self.store.servers)
        box.append(Gtk.Label(label="Keine offene Verbindung" if has_servers else "Noch keine Server",
                             xalign=0, css_classes=["pb-title"]))
        box.append(Gtk.Label(
            label="Wähle links einen Server oder tippe einfach los, um zu suchen."
            if has_servers else
            "Lege deinen ersten Server an oder übernimm Hosts aus deiner SSH-Konfiguration.",
            xalign=0, wrap=True, css_classes=["pb-quiet"],
        ))

        recent = self.store.recent()
        self._welcome_rows = []
        if recent:
            box.append(Gtk.Label(label="Zuletzt verbunden", xalign=0, margin_top=20, css_classes=["pb-section-label"]))
            lb = Gtk.ListBox(css_classes=["pb-ports"], selection_mode=Gtk.SelectionMode.NONE)
            for server in recent:
                row = ServerRow(server, self.theme, with_menu=False)
                row.set_status(self.status.states.get(server.id, Status.CHECKING))
                self._welcome_rows.append(row)
                lb.append(row)
            lb.connect("row-activated", lambda _lb, row: self.connect_server(row.server))
            box.append(lb)

        # FlowBox bricht auf schmalen Fenstern (Deck hochkant) in zwei Zeilen um.
        actions = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=8, row_spacing=8,
                              max_children_per_line=2, margin_top=24, halign=Gtk.Align.START)
        add = Gtk.Button(label="Server hinzufügen", action_name="win.new-server", css_classes=["suggested-action"])
        imp = Gtk.Button(label="Aus ~/.ssh/config importieren", action_name="win.import")
        for button in (add, imp):
            actions.append(button)
            button.get_parent().set_focusable(False)  # Fokus direkt auf den Button, nicht auf die Hülle
        box.append(actions)
        return clamp

    # Liste --------------------------------------------------------------

    def rebuild_list(self) -> None:
        self.listbox.remove_all()
        self._rows.clear()
        ungrouped = [s for s in self.store.servers if not s.group]
        grouped = sorted((s for s in self.store.servers if s.group), key=lambda s: s.group.lower())
        for server in ungrouped + grouped:  # sorted() ist stabil: Reihenfolge innerhalb der Gruppe bleibt
            row = ServerRow(server, self.theme)
            row.set_status(self.status.states.get(server.id, Status.CHECKING))
            self._rows[server.id] = row
            self.listbox.append(row)
        self._update_placeholder()
        self.listbox.invalidate_headers()
        if self.stack.get_visible_child_name() == "welcome":
            self.welcome.set_child(self._build_welcome())

    def _header(self, row: ServerRow, before: ServerRow | None) -> None:
        group = row.server.group
        if group and (before is None or before.server.group != group):
            row.set_header(group_header(group))
        else:
            row.set_header(None)

    def _filter(self, row: ServerRow) -> bool:
        if not self._query:
            return True
        s = row.server
        return any(self._query in field.lower() for field in (s.name, s.host, s.group, s.user))

    def _search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._query = entry.get_text().strip().lower()
        self.listbox.invalidate_filter()
        self.listbox.invalidate_headers()
        self._update_placeholder()
        first = self._first_visible()
        if first and self._query:
            self.listbox.select_row(first)

    def _first_visible(self) -> ServerRow | None:
        return next((r for r in self._ordered_rows() if self._filter(r)), None)

    def _ordered_rows(self):
        i = 0
        while (row := self.listbox.get_row_at_index(i)) is not None:
            yield row
            i += 1

    def _search_activate(self, *_):
        row = self.listbox.get_selected_row() or self._first_visible()
        if row and self._filter(row):
            self.connect_server(row.server)

    def _update_placeholder(self) -> None:
        if not self.store.servers:
            self._placeholder.set_label("Noch keine Server gespeichert.")
        else:
            self._placeholder.set_label(f"Kein Server passt zu „{self.search.get_text().strip()}“.")

    def _status_changed(self, server_id: str, status: Status) -> None:
        rows = [self._rows.get(server_id)] + [r for r in self._welcome_rows if r.server.id == server_id]
        for row in filter(None, rows):
            row.set_status(status)

    # Inhalt rechts ------------------------------------------------------

    def _update_content(self) -> None:
        has_tabs = self.tabview.get_n_pages() > 0
        self.tabbar.set_visible(has_tabs)
        if has_tabs:
            self.stack.set_visible_child_name("tabs")
            self.search.set_key_capture_widget(self.sidebar_view)
        else:
            self.welcome.set_child(self._build_welcome())
            self.stack.set_visible_child_name("welcome")
            # Ohne Terminal darf man überall einfach lostippen.
            self.search.set_key_capture_widget(self)
        self._sync_sidebar_button()

    def _sync_sidebar_button(self) -> None:
        self.sidebar_button.set_visible(self.split.get_collapsed())

    def _focus_terminal(self) -> None:
        page = self.tabview.get_selected_page()
        if page:
            page.set_needs_attention(False)
            page.get_child().terminal.grab_focus()

    # Verbinden ----------------------------------------------------------

    def connect_server(self, server: Server, *, remember: bool = True) -> None:
        if not connection.ssh_available():
            self.toast("Kein ssh-Client gefunden. Installiere OpenSSH oder starte Patchbay als Flatpak.")
            return
        argv = connection.connect_argv(server, self.store.find_by_name)
        target = f"{server.host}:{server.port}"
        self._open_tab(server, argv, server.name, target)
        if remember and self.store.get(server.id):
            self.store.mark_connected(server.id)
        if self.split.get_collapsed():
            self.split.set_show_sidebar(False)

    def _open_tab(self, server: Server, argv: list[str], title: str, target: str, **texts) -> TerminalPage:
        page_widget = TerminalPage(
            argv, self.theme, self.store.settings["terminal_font"], target,
            on_reconnect=lambda p: p.spawn(), **texts,
        )
        page_widget.server = server
        page = self.tabview.append(page_widget)
        page.set_title(title)
        page.set_tooltip(server.address)
        page.set_icon(stripe_icon(server.color))
        page_widget.terminal.connect("child-exited", lambda *_: self._mark_exited(page))
        self.tabview.set_selected_page(page)
        page_widget.terminal.grab_focus()
        return page_widget

    def _mark_exited(self, page: Adw.TabPage) -> None:
        if page != self.tabview.get_selected_page():
            page.set_needs_attention(True)

    def _close_page(self, view: Adw.TabView, page: Adw.TabPage) -> bool:
        self.theme.off(page.get_child().apply_colors)
        view.close_page_finish(page, True)  # Prozess endet mit dem PTY (SIGHUP)
        return Gdk.EVENT_STOP

    def quick_connect(self, text: str) -> None:
        saved = self.store.find_by_name(text)
        if saved:
            self.connect_server(saved)
            return
        server = connection.parse_quick_target(text)
        if not server:
            self.toast(f"„{text.strip()}“ ist keine gültige Adresse. Beispiel: max@192.168.1.20:22")
            return
        self.connect_server(server, remember=False)

    def copy_key(self, server: Server) -> None:
        pub = connection.find_public_key(server)
        if not pub:
            self.toast("Kein öffentlicher Key gefunden. Erzeuge einen mit ssh-keygen "
                       "oder wähle im Server einen Key, neben dem eine .pub-Datei liegt.")
            return
        try:
            key = connection.read_public_key(pub)
        except (OSError, ValueError) as err:
            self.toast(str(err))
            return
        argv = connection.copy_id_argv(server, key, self.store.find_by_name)
        self._open_tab(
            server, argv, f"Key kopieren: {server.name}", f"{server.host}:{server.port}",
            success_text=f"{pub.name} ist auf {server.name} eingetragen. Ab jetzt geht es ohne Passwort.",
        )

    # Aktionen -----------------------------------------------------------

    def _install_actions(self) -> None:
        simple = {
            "new-server": lambda: self.edit_server(None),
            "quick-connect": lambda: quick_connect_dialog(self.quick_connect).present(self),
            "close-tab": self._close_current_tab,
            "tab-reconnect": self._reconnect_current,
            "search": self._focus_search,
            "import": lambda: ImportDialog(self.store, self._import_servers).present(self),
            "terminal-font": self._choose_font,
            "shortcuts": lambda: shortcuts_dialog().present(self),
            "about": self._about,
        }
        for name, cb in simple.items():
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", lambda *_a, cb=cb: cb())
            self.add_action(act)

        per_server = {
            "server-connect": self.connect_server,
            "server-edit": self.edit_server,
            "server-duplicate": self._duplicate,
            "server-copy-command": self._copy_command,
            "server-copy-id": self.copy_key,
            "server-delete": self._delete,
        }
        for name, cb in per_server.items():
            act = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            act.connect("activate", self._server_action, cb)
            self.add_action(act)

    def _server_action(self, _act, param: GLib.Variant, cb) -> None:
        server = self.store.get(param.get_string())
        if server:
            cb(server)

    def _install_shortcuts(self) -> None:
        def add(controller, accel, action):
            controller.add_shortcut(Gtk.Shortcut(
                trigger=Gtk.ShortcutTrigger.parse_string(accel),
                action=Gtk.NamedAction.new(action),
            ))

        # Bubble-Phase: Hat das Terminal den Fokus, bekommt die Shell Strg+W/N/T/F
        # (Wort löschen, History, …). Überall sonst greifen die App-Kürzel.
        bubble = Gtk.ShortcutController(propagation_phase=Gtk.PropagationPhase.BUBBLE, scope=Gtk.ShortcutScope.GLOBAL)
        for accel, action in (("<Control>n", "win.new-server"), ("<Control>t", "win.quick-connect"),
                              ("<Control>w", "win.close-tab"), ("<Control>f", "win.search")):
            add(bubble, accel, action)
        self.add_controller(bubble)

        # Capture-Phase: funktioniert immer, auch im Terminal.
        capture = Gtk.ShortcutController(propagation_phase=Gtk.PropagationPhase.CAPTURE, scope=Gtk.ShortcutScope.GLOBAL)
        for accel, action in (("<Control><Shift>n", "win.new-server"), ("<Control><Shift>t", "win.quick-connect"),
                              ("<Control><Shift>w", "win.close-tab"), ("<Control><Shift>f", "win.search"),
                              ("<Control>question", "win.shortcuts"), ("<Control><Shift>question", "win.shortcuts")):
            add(capture, accel, action)
        self.add_controller(capture)

    def _focus_search(self) -> None:
        if self.split.get_collapsed():
            self.split.set_show_sidebar(True)
        self.search.grab_focus()

    def _close_current_tab(self) -> None:
        page = self.tabview.get_selected_page()
        if page:
            self.tabview.close_page(page)

    def _reconnect_current(self) -> None:
        page = self.tabview.get_selected_page()
        if page:
            page.get_child().spawn()

    # Server bearbeiten --------------------------------------------------

    def edit_server(self, server: Server | None) -> None:
        def saved(new: Server) -> None:
            self.store.upsert(new)
            self.rebuild_list()
            self.status.forget(new.id)
            self.status.check(new)
            row = self._rows.get(new.id)
            if row:
                self.listbox.select_row(row)
            self.toast(f"„{new.name}“ gespeichert.")

        ServerEditor(self.store, server, saved).present(self)

    def _duplicate(self, server: Server) -> None:
        copy = self.store.duplicate(server.id)
        self.rebuild_list()
        self.status.check(copy)
        self.edit_server(copy)

    def _copy_command(self, server: Server) -> None:
        cmd = connection.command_string(server, self.store.find_by_name)
        self.get_clipboard().set(cmd)
        self.toast(f"Befehl kopiert: {cmd}")

    def _delete(self, server: Server) -> None:
        index = self.store.servers.index(server)
        self.store.remove(server.id)
        self.status.forget(server.id)
        self.rebuild_list()

        def undo(*_):
            self.store.servers.insert(index, server)
            self.store.save()
            self.rebuild_list()
            self.status.check(server)

        toast = Adw.Toast(title=f"„{server.name}“ gelöscht.", button_label="Rückgängig")
        toast.connect("button-clicked", undo)
        self.toasts.add_toast(toast)

    def _import_servers(self, servers: list[Server]) -> None:
        for server in servers:
            self.store.servers.append(server)
        self.store.save()
        self.rebuild_list()
        for server in servers:
            self.status.check(server)
        self.toast("1 Server importiert." if len(servers) == 1 else f"{len(servers)} Server importiert.")

    # Sonstiges ----------------------------------------------------------

    def _choose_font(self) -> None:
        dialog = Gtk.FontDialog(title="Terminal-Schrift")
        initial = Pango.FontDescription.from_string(self.store.settings["terminal_font"])

        def done(dlg, result):
            try:
                desc = dlg.choose_font_finish(result)
            except GLib.Error:
                return
            font = desc.to_string()
            self.store.settings["terminal_font"] = font
            self.store.save()
            for i in range(self.tabview.get_n_pages()):
                self.tabview.get_nth_page(i).get_child().set_font(font)

        dialog.choose_font(self, initial, None, done)

    def _about(self) -> None:
        from .. import APP_ID, VERSION
        about = Adw.AboutDialog(
            application_name="Patchbay", application_icon=APP_ID, version=VERSION,
            developer_name="Max", license_type=Gtk.License.GPL_3_0,
            comments="SSH-Server speichern, verwalten und mit einem Klick verbinden.",
        )
        about.present(self)

    def toast(self, text: str, timeout: int = 4) -> None:
        self.toasts.add_toast(Adw.Toast(title=text, timeout=timeout, use_markup=False))

    def _on_close(self, *_):
        self.status.stop()
        return False

