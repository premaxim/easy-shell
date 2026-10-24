"""Key nach einem Passwort-Login automatisch auf den Server übertragen.

Ablauf pro Sitzung:
1. Die Terminal-Sitzung läuft als ssh-ControlMaster mit eigenem Socket.
2. Der Socket entsteht erst nach erfolgreicher Anmeldung – dann ist der Nutzer drin.
3. Eine zweite Verbindung versucht nur Keys (BatchMode). Wird sie abgewiesen,
   lief der Login per Passwort.
4. Der öffentliche Key wird über den bestehenden Master eingetragen – ohne
   dass das Passwort noch einmal abgefragt wird.
Läuft alles nebenläufig über Gio.Subprocess, die Oberfläche blockiert nie.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Callable

from gi.repository import Gio, GLib

from ..models import Server
from . import connection
from .connection import Resolver

POLL_MS = 1000
GIVE_UP_AFTER_S = 15 * 60  # so lange darf die Passwort-Eingabe dauern


class Probe(Enum):
    KEY_WORKS = "key-works"
    NEEDS_PASSWORD = "needs-password"
    UNKNOWN = "unknown"


class Outcome(Enum):
    ADDED = "added"
    ALREADY_PRESENT = "present"
    NO_PUBLIC_KEY = "no-public-key"
    FAILED = "failed"


def classify_probe(exit_code: int, stderr: str) -> Probe:
    if exit_code == 0:
        return Probe.KEY_WORKS
    if exit_code == 255 and "permission denied" in stderr.lower():
        return Probe.NEEDS_PASSWORD
    return Probe.UNKNOWN  # Netzwerk, Host-Key, Timeout … – dann lieber nichts tun


def classify_push(exit_code: int, stdout: str) -> Outcome:
    if exit_code == 0 and connection.KEY_ADDED in stdout:
        return Outcome.ADDED
    if exit_code == 0 and connection.KEY_PRESENT in stdout:
        return Outcome.ALREADY_PRESENT
    return Outcome.FAILED


Report = Callable[[Server, Outcome, str], None]


class AutoKeyWatch:
    """Beobachtet eine Sitzung. ``alive`` meldet, ob Tab und Prozess noch bestehen."""

    def __init__(self, server: Server, control_path: Path, resolve: Resolver,
                 alive: Callable[[], bool], report: Report):
        self.server = server
        self.control_path = control_path
        self._resolve = resolve
        self._alive = alive
        self._report = report
        self._waited_ms = 0
        self._source = GLib.timeout_add(POLL_MS, self._poll)

    def cancel(self) -> None:
        if self._source:
            GLib.source_remove(self._source)
            self._source = None

    def _poll(self) -> bool:
        self._waited_ms += POLL_MS
        if not self._alive() or self._waited_ms > GIVE_UP_AFTER_S * 1000:
            self._source = None
            return GLib.SOURCE_REMOVE
        if not self.control_path.exists():
            return GLib.SOURCE_CONTINUE
        self._source = None
        self._run(connection.pubkey_probe_argv(self.server, self._resolve), self._probe_done)
        return GLib.SOURCE_REMOVE

    def _probe_done(self, code: int, _out: str, err: str) -> None:
        if classify_probe(code, err) is not Probe.NEEDS_PASSWORD or not self._alive():
            return
        pub = connection.find_public_key(self.server)
        if not pub:
            self._report(self.server, Outcome.NO_PUBLIC_KEY, "")
            return
        try:
            key = connection.read_public_key(pub)
        except (OSError, ValueError) as exc:
            self._report(self.server, Outcome.FAILED, str(exc))
            return
        argv = connection.copy_id_via_master_argv(self.server, key, self.control_path, self._resolve)
        self._run(argv, lambda c, o, e: self._report(self.server, classify_push(c, o), pub.name if c == 0 else e.strip()))

    @staticmethod
    def _run(argv: list[str], done: Callable[[int, str, str], None]) -> None:
        try:
            proc = Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
                                      | Gio.SubprocessFlags.STDIN_PIPE)
        except GLib.Error as exc:
            done(-1, "", exc.message)
            return

        def finished(p, result):
            try:
                _ok, out, err = p.communicate_utf8_finish(result)
            except GLib.Error as exc:
                done(-1, "", exc.message)
                return
            done(p.get_exit_status() if p.get_if_exited() else -1, out or "", err or "")

        proc.communicate_utf8_async(None, None, finished)
