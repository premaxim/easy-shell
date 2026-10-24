"""Asynchroner TCP-Check auf den SSH-Port. Blockiert nie die Oberfläche."""

from __future__ import annotations

from enum import Enum
from typing import Callable

from gi.repository import Gio, GLib

from ..models import DEFAULT_PORT, Server
from .connection import Resolver

INTERVAL_SECONDS = 30
TIMEOUT_SECONDS = 4


class Status(Enum):
    CHECKING = "checking"
    ONLINE = "online"
    OFFLINE = "offline"


LABELS = {
    Status.CHECKING: "Prüfe…",
    Status.ONLINE: "Erreichbar",
    Status.OFFLINE: "Nicht erreichbar",
}


def probe_target(server: Server, resolve: Resolver | None) -> tuple[str, int]:
    """Mit Jump-Host ist das Ziel direkt oft nicht erreichbar – dann prüfen wir den ersten Hop."""
    if not server.jump_host:
        return server.host, server.port
    first = server.jump_host.split(",")[0].strip()
    saved = resolve(first) if resolve else None
    if saved:
        return saved.host, saved.port
    hostpart = first.rsplit("@", 1)[-1]
    if hostpart.startswith("["):
        host, _, rest = hostpart[1:].partition("]")
        port = rest.lstrip(":")
    else:
        host, _, port = hostpart.partition(":")
    return host, int(port) if port.isdigit() else DEFAULT_PORT


class StatusMonitor:
    def __init__(self, on_change: Callable[[str, Status], None], resolve: Resolver):
        self._on_change = on_change
        self._resolve = resolve
        self._cancellable = Gio.Cancellable()
        self._source: int | None = None
        self._servers: Callable[[], list[Server]] = lambda: []
        self.states: dict[str, Status] = {}

    def start(self, servers: Callable[[], list[Server]]) -> None:
        self._servers = servers
        self.check_all()
        self._source = GLib.timeout_add_seconds(INTERVAL_SECONDS, self._tick)

    def stop(self) -> None:
        self._cancellable.cancel()
        if self._source:
            GLib.source_remove(self._source)
            self._source = None

    def _tick(self) -> bool:
        self.check_all()
        return GLib.SOURCE_CONTINUE

    def check_all(self) -> None:
        for server in self._servers():
            self.check(server)

    def check(self, server: Server) -> None:
        # Beim ersten Mal „prüfe…“, danach bleibt der letzte Zustand stehen,
        # bis das Ergebnis da ist – sonst flackern alle LEDs alle 30 s.
        if server.id not in self.states:
            self._set(server.id, Status.CHECKING)
        host, port = probe_target(server, self._resolve)
        client = Gio.SocketClient(timeout=TIMEOUT_SECONDS)
        client.connect_to_host_async(host, port, self._cancellable, self._done, server.id)

    def _done(self, client: Gio.SocketClient, result: Gio.AsyncResult, server_id: str) -> None:
        try:
            conn = client.connect_to_host_finish(result)
            conn.close_async(GLib.PRIORITY_DEFAULT, None, None, None)
            state = Status.ONLINE
        except GLib.Error as err:
            if err.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                return
            state = Status.OFFLINE
        self._set(server_id, state)

    def _set(self, server_id: str, state: Status) -> None:
        if self.states.get(server_id) != state:
            self.states[server_id] = state
            self._on_change(server_id, state)

    def forget(self, server_id: str) -> None:
        self.states.pop(server_id, None)
