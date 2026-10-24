"""JSON-Speicher unter $XDG_CONFIG_HOME/patchbay/servers.json.

Passwörter werden nie gespeichert – das Modell hat dafür gar kein Feld.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .models import Server

FORMAT_VERSION = 1
DEFAULT_SETTINGS = {"terminal_font": "JetBrains Mono 11"}


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "patchbay"


class ServerStore:
    """Lädt und speichert Server sowie die wenigen App-Einstellungen."""

    def __init__(self, path: Path | None = None):
        self.path = path or config_dir() / "servers.json"
        self.servers: list[Server] = []
        self.settings: dict = dict(DEFAULT_SETTINGS)
        # Gesetzt, wenn beim Laden etwas repariert werden musste.
        self.load_warning: str | None = None

    # Laden / Speichern -------------------------------------------------

    def load(self) -> None:
        self.servers = []
        self.settings = dict(DEFAULT_SETTINGS)
        self.load_warning = None
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Oberste Ebene ist kein Objekt")
        except (OSError, ValueError) as err:
            backup = self.path.with_name(f"servers.json.defekt-{int(time.time())}")
            try:
                self.path.rename(backup)
            except OSError:
                backup = None
            self.load_warning = (
                f"Die Serverliste war nicht lesbar ({err}). "
                + (f"Eine Sicherung liegt unter {backup}." if backup else "")
            ).strip()
            return

        skipped = 0
        for raw in data.get("servers", []):
            try:
                self.servers.append(Server.from_dict(raw))
            except (TypeError, ValueError, AttributeError):
                skipped += 1
        if skipped:
            self.load_warning = f"{skipped} Einträge ohne Name oder Host wurden übersprungen."
        settings = data.get("settings")
        if isinstance(settings, dict):
            self.settings.update({k: v for k, v in settings.items() if k in DEFAULT_SETTINGS})

    def save(self) -> None:
        """Atomar schreiben: erst Temp-Datei, dann umbenennen. Nur für den Nutzer lesbar."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": FORMAT_VERSION,
            "servers": [s.to_dict() for s in self.servers],
            "settings": self.settings,
        }
        tmp = self.path.with_suffix(".json.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    # Bearbeiten --------------------------------------------------------

    def get(self, server_id: str) -> Server | None:
        return next((s for s in self.servers if s.id == server_id), None)

    def find_by_name(self, name: str) -> Server | None:
        name = name.strip().lower()
        return next((s for s in self.servers if s.name.lower() == name), None)

    def upsert(self, server: Server) -> None:
        for i, existing in enumerate(self.servers):
            if existing.id == server.id:
                self.servers[i] = server
                break
        else:
            self.servers.append(server)
        self.save()

    def remove(self, server_id: str) -> Server | None:
        server = self.get(server_id)
        if server:
            self.servers.remove(server)
            self.save()
        return server

    def duplicate(self, server_id: str) -> Server | None:
        server = self.get(server_id)
        if not server:
            return None
        copy = server.duplicate()
        self.servers.insert(self.servers.index(server) + 1, copy)
        self.save()
        return copy

    def mark_connected(self, server_id: str) -> None:
        server = self.get(server_id)
        if server:
            server.last_connected = time.time()
            self.save()

    def recent(self, limit: int = 5) -> list[Server]:
        used = [s for s in self.servers if s.last_connected]
        return sorted(used, key=lambda s: s.last_connected, reverse=True)[:limit]

    def groups(self) -> list[str]:
        return sorted({s.group for s in self.servers if s.group}, key=str.lower)

    def color_for_group(self, group: str) -> str | None:
        """Häufigste Kabelfarbe einer Gruppe – Vorschlag für neue Server."""
        colors = [s.color for s in self.servers if s.group == group]
        return max(set(colors), key=colors.count) if colors else None

    def contains_equivalent(self, host: str, port: int, user: str) -> bool:
        return any(
            s.host.lower() == host.lower() and s.port == port and s.user == user
            for s in self.servers
        )
