"""Baut ssh-Aufrufe aus gespeicherten Servern.

Die GNOME-Runtime bringt einen ssh-Client mit, daher läuft ssh normalerweise
direkt in der Sandbox. Fehlt er (andere Runtime, eigener Build), weicht
Patchbay auf ``flatpak-spawn --host ssh`` aus. Dafür braucht das Flatpak die
Permission ``--talk-name=org.freedesktop.Flatpak`` (siehe README).
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
from pathlib import Path
from typing import Callable

from ..models import DEFAULT_PORT, Server

Resolver = Callable[[str], Server | None]

IN_FLATPAK = os.path.exists("/.flatpak-info")
PUBKEY_CANDIDATES = ("id_ed25519.pub", "id_ecdsa.pub", "id_rsa.pub")


def host_prefix(program: str = "ssh") -> list[str]:
    if shutil.which(program) is None and IN_FLATPAK:
        return ["flatpak-spawn", "--host", program]
    return [program]


def ssh_available() -> bool:
    return shutil.which("ssh") is not None or (IN_FLATPAK and shutil.which("flatpak-spawn") is not None)


def _jump_spec(server: Server) -> str:
    port = f":{server.port}" if server.port != DEFAULT_PORT else ""
    return f"{server.target}{port}"


def resolve_jump(jump: str, resolve: Resolver | None) -> str:
    """Ein Jump-Host darf der Name eines gespeicherten Servers sein."""
    hops = []
    for hop in (h.strip() for h in jump.split(",")):
        if not hop:
            continue
        saved = resolve(hop) if resolve else None
        hops.append(_jump_spec(saved) if saved else hop)
    return ",".join(hops)


def ssh_args(server: Server, resolve: Resolver | None = None) -> list[str]:
    """Argumente ohne Programmname – Basis für Verbinden, Kopieren und Key kopieren."""
    args: list[str] = []
    if server.port != DEFAULT_PORT:
        args += ["-p", str(server.port)]
    if server.key_path:
        args += ["-i", os.path.expanduser(server.key_path), "-o", "IdentitiesOnly=yes"]
    if server.jump_host:
        jump = resolve_jump(server.jump_host, resolve)
        if jump:
            args += ["-J", jump]
    args.append(server.target)
    return args


def connect_argv(server: Server, resolve: Resolver | None = None) -> list[str]:
    return host_prefix() + ssh_args(server, resolve)


def command_string(server: Server, resolve: Resolver | None = None) -> str:
    """Fertiger Befehl für die Zwischenablage – ohne flatpak-spawn, zum Einfügen in jedes Terminal."""
    return shlex.join(["ssh", *ssh_args(server, resolve)])


# Key auf Server kopieren ------------------------------------------------

def find_public_key(server: Server) -> Path | None:
    if server.key_path:
        candidate = Path(os.path.expanduser(server.key_path))
        if candidate.suffix != ".pub":
            candidate = candidate.with_name(candidate.name + ".pub")
        return candidate if candidate.is_file() else None
    ssh_dir = Path.home() / ".ssh"
    return next((ssh_dir / n for n in PUBKEY_CANDIDATES if (ssh_dir / n).is_file()), None)


_PUBKEY = re.compile(r"^(ssh-|ecdsa-|sk-)[\w@.-]+ [A-Za-z0-9+/=]+( [^\n]*)?$")


def read_public_key(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if "\n" in text or not _PUBKEY.match(text):
        raise ValueError(f"{path} sieht nicht wie ein öffentlicher SSH-Key aus.")
    return text


def copy_id_argv(server: Server, pubkey: str, resolve: Resolver | None = None) -> list[str]:
    """Entspricht ssh-copy-id: Key anhängen, wenn er noch nicht eingetragen ist.

    ssh-copy-id ist nicht in der Runtime enthalten, daher bauen wir den
    Remote-Befehl selbst. Ein Passwort-Prompt erscheint im Terminal.
    """
    quoted = shlex.quote(pubkey)
    remote = (
        "umask 077; mkdir -p ~/.ssh && touch ~/.ssh/authorized_keys && "
        f"if grep -qxF {quoted} ~/.ssh/authorized_keys; then echo 'Key war schon eingetragen.'; "
        f"else printf '%s\\n' {quoted} >> ~/.ssh/authorized_keys && echo 'Key eingetragen.'; fi"
    )
    return host_prefix() + [*ssh_args(server, resolve), remote]


# Schnellverbinden -------------------------------------------------------

_QUICK = re.compile(r"^(?:(?P<user>[^@\s]+)@)?(?P<host>\[[^\]]+\]|[^:\s]+)(?::(?P<port>\d{1,5}))?$")


def parse_quick_target(text: str) -> Server | None:
    """``[user@]host[:port]`` → temporärer Server. IPv6 in eckigen Klammern."""
    text = text.strip()
    if text.startswith("ssh "):
        text = text[4:].strip()
    match = _QUICK.match(text)
    if not match:
        return None
    host = match["host"].strip("[]")
    port = int(match["port"]) if match["port"] else DEFAULT_PORT
    if not 1 <= port <= 65535:
        return None
    return Server(name=host, host=host, port=port, user=match["user"] or "")
