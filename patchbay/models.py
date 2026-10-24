"""Datenmodell für gespeicherte Server."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field, fields

# Kabelfarben wie echte Netzwerkkabel. Schlüssel werden gespeichert,
# die Hex-Werte nur in der Oberfläche verwendet.
CABLE_COLORS: dict[str, tuple[str, str]] = {
    "blue": ("Blau", "#4A8BD4"),
    "yellow": ("Gelb", "#D9B95B"),
    "grey": ("Grau", "#9AA7B1"),
    "red": ("Rot", "#CC6470"),
    "green": ("Grün", "#5DB98C"),
    "violet": ("Violett", "#9B7FD1"),
}
DEFAULT_COLOR = "blue"
DEFAULT_PORT = 22


@dataclass
class Server:
    name: str
    host: str
    port: int = DEFAULT_PORT
    user: str = ""
    key_path: str = ""
    jump_host: str = ""
    group: str = ""
    color: str = DEFAULT_COLOR
    notes: str = ""
    last_connected: float | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def target(self) -> str:
        """``user@host`` bzw. nur ``host``, wie ssh es erwartet."""
        return f"{self.user}@{self.host}" if self.user else self.host

    @property
    def address(self) -> str:
        """Leise Unterzeile in der Liste: ``user@host`` plus Port, falls ≠ 22."""
        port = f":{self.port}" if self.port != DEFAULT_PORT else ""
        return f"{self.target}{port}"

    def duplicate(self) -> "Server":
        data = asdict(self)
        data.pop("id")
        data["name"] = f"{self.name} (Kopie)"
        data["last_connected"] = None
        return Server(**data)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Server":
        """Tolerant gegenüber fehlenden oder unbekannten Feldern."""
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in data.items() if k in known}
        if not clean.get("name") or not clean.get("host"):
            raise ValueError("Server braucht mindestens Name und Host")
        try:
            clean["port"] = int(clean.get("port", DEFAULT_PORT))
        except (TypeError, ValueError):
            clean["port"] = DEFAULT_PORT
        if not 1 <= clean["port"] <= 65535:
            clean["port"] = DEFAULT_PORT
        if clean.get("color") not in CABLE_COLORS:
            clean["color"] = DEFAULT_COLOR
        for key in ("name", "host", "user", "key_path", "jump_host", "group", "notes"):
            if key in clean:
                clean[key] = str(clean[key] or "").strip() if key != "notes" else str(clean[key] or "")
        return cls(**clean)
