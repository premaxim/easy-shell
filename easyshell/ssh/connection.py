"""Baut ssh-Aufrufe aus gespeicherten Servern.

Die GNOME-Runtime bringt einen ssh-Client mit, daher läuft ssh normalerweise
direkt in der Sandbox. Fehlt er (andere Runtime, eigener Build), weicht
easyShell auf ``flatpak-spawn --host ssh`` aus. Dafür braucht das Flatpak die
Permission ``--talk-name=org.freedesktop.Flatpak`` (siehe README).
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import uuid
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


def connect_argv(server: Server, resolve: Resolver | None = None, control_path: Path | None = None) -> list[str]:
    """Mit ``control_path`` wird die Sitzung ein ssh-ControlMaster: Weitere Befehle
    (z. B. Key übertragen) laufen über die bestehende Verbindung, ohne erneute Anmeldung."""
    control = ["-o", "ControlMaster=yes", "-o", f"ControlPath={control_path}", "-o", "ControlPersist=no"] \
        if control_path else []
    return host_prefix() + control + ssh_args(server, resolve)


# ControlMaster ----------------------------------------------------------

def multiplexing_available() -> bool:
    """Über flatpak-spawn läge der Socket außerhalb der Sandbox – dann ohne Multiplexing."""
    return host_prefix() == ["ssh"]


def new_control_path() -> Path:
    """Eindeutiger Socket pro Sitzung. Kurz halten: Unix-Sockets erlauben max. 108 Zeichen."""
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
    app_id = os.environ.get("FLATPAK_ID")
    base = runtime / "app" / app_id if app_id and (runtime / "app" / app_id).is_dir() else runtime / "easyshell"
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    return base / f"cm-{uuid.uuid4().hex[:12]}"


def pubkey_probe_argv(server: Server, resolve: Resolver | None = None) -> list[str]:
    """Neue Verbindung, die nur Keys versucht und nie nachfragt. Scheitert sie mit
    „Permission denied“, hat ein Key allein nicht gereicht – der Login lief per Passwort."""
    return host_prefix() + [
        "-o", "BatchMode=yes", "-o", "PreferredAuthentications=publickey",
        "-o", "ControlMaster=no", "-o", "ControlPath=none", "-o", "ConnectTimeout=10",
        *ssh_args(server, resolve), "true",
    ]


def copy_id_via_master_argv(server: Server, pubkey: str, control_path: Path,
                            resolve: Resolver | None = None) -> list[str]:
    return host_prefix() + [
        "-o", "ControlMaster=no", "-o", f"ControlPath={control_path}", "-o", "BatchMode=yes",
        *ssh_args(server, resolve), copy_id_remote_command(pubkey),
    ]


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


KEY_ADDED = "EASYSHELL_KEY_ADDED"
KEY_PRESENT = "EASYSHELL_KEY_PRESENT"


def copy_id_remote_command(pubkey: str, added: str = KEY_ADDED, present: str = KEY_PRESENT) -> str:
    """Entspricht ssh-copy-id: Key anhängen, wenn er noch nicht eingetragen ist.
    ssh-copy-id ist nicht in der Runtime enthalten, daher bauen wir den Befehl selbst."""
    quoted = shlex.quote(pubkey)
    return (
        "umask 077; mkdir -p ~/.ssh && touch ~/.ssh/authorized_keys && "
        f"if grep -qxF {quoted} ~/.ssh/authorized_keys; then echo {shlex.quote(present)}; "
        f"else printf '%s\\n' {quoted} >> ~/.ssh/authorized_keys && echo {shlex.quote(added)}; fi"
    )


def copy_id_argv(server: Server, pubkey: str, resolve: Resolver | None = None) -> list[str]:
    """Manuelles „Key auf Server kopieren“ im Terminal-Tab – ein Passwort-Prompt erscheint dort."""
    remote = copy_id_remote_command(pubkey, added="Key eingetragen.", present="Key war schon eingetragen.")
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
