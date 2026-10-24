"""Minimaler Parser für ~/.ssh/config – nur zum Importieren.

Bildet die ssh-Semantik nach, soweit sie für den Import relevant ist:
Schlüssel ohne Groß-/Kleinschreibung, ``Key Wert`` und ``Key=Wert``,
Anführungszeichen, ``Include`` (relativ zu ~/.ssh, mit Globs), Muster mit
Negation, und „erster gefundener Wert gewinnt“. ``Match``-Blöcke werden
übersprungen, weil sie sich ohne Verbindung nicht auswerten lassen.
"""

from __future__ import annotations

import fnmatch
import re
import glob
import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from ..models import DEFAULT_PORT

WANTED = {"hostname", "port", "user", "identityfile", "proxyjump"}
MAX_INCLUDE_DEPTH = 8
_LINE = re.compile(r"^([^\s=]+)(?:\s*=\s*|\s+)(.*)$")


@dataclass
class Block:
    patterns: list[str] | None  # None = Match-Block (ignoriert)
    options: list[tuple[str, str]]


@dataclass
class ImportCandidate:
    alias: str
    host: str
    port: int = DEFAULT_PORT
    user: str = ""
    key_path: str = ""
    jump_host: str = ""


def _split(line: str) -> tuple[str, list[str]] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    # "Key Wert", "Key=Wert" und "Key = Wert" erlauben
    match = _LINE.match(line)
    if not match:
        return line.lower(), []
    key, rest = match.groups()
    try:
        values = shlex.split(rest, comments=True)
    except ValueError:
        values = rest.split()
    return key.strip().lower(), values


def _read_blocks(path: Path, ssh_dir: Path, depth: int = 0, blocks: list[Block] | None = None) -> list[Block]:
    if blocks is None:
        blocks = [Block(patterns=["*"], options=[])]  # Optionen vor dem ersten Host gelten global
    if depth > MAX_INCLUDE_DEPTH:
        return blocks
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return blocks
    for line in lines:
        parsed = _split(line)
        if not parsed:
            continue
        key, values = parsed
        if key == "host":
            blocks.append(Block(patterns=values, options=[]))
        elif key == "match":
            blocks.append(Block(patterns=None, options=[]))
        elif key == "include":
            for value in values:
                pattern = os.path.expanduser(value)
                if not os.path.isabs(pattern):
                    pattern = str(ssh_dir / pattern)
                for inc in sorted(glob.glob(pattern)):
                    _read_blocks(Path(inc), ssh_dir, depth + 1, blocks)
        elif key in WANTED and values:
            blocks[-1].options.append((key, " ".join(values) if key != "identityfile" else values[0]))
    return blocks


def _matches(alias: str, patterns: list[str]) -> bool:
    matched = False
    for pat in patterns:
        if pat.startswith("!"):
            if fnmatch.fnmatchcase(alias, pat[1:]):
                return False
        elif fnmatch.fnmatchcase(alias, pat):
            matched = True
    return matched


def _is_concrete(pattern: str) -> bool:
    return not pattern.startswith("!") and not any(c in pattern for c in "*?")


def parse_ssh_config(path: Path | None = None) -> list[ImportCandidate]:
    """Liefert einen Kandidaten pro konkretem Host-Alias, in Dateireihenfolge."""
    path = path or Path.home() / ".ssh" / "config"
    ssh_dir = path.parent
    blocks = _read_blocks(path, ssh_dir)

    aliases: list[str] = []
    for block in blocks:
        for pat in block.patterns or []:
            if _is_concrete(pat) and pat not in aliases:
                aliases.append(pat)

    result = []
    for alias in aliases:
        resolved: dict[str, str] = {}
        for block in blocks:
            if block.patterns is None or not _matches(alias, block.patterns):
                continue
            for key, value in block.options:
                resolved.setdefault(key, value)  # erster Wert gewinnt
        try:
            port = int(resolved.get("port", DEFAULT_PORT))
        except ValueError:
            port = DEFAULT_PORT
        key_path = resolved.get("identityfile", "")
        if key_path:
            key_path = os.path.expanduser(key_path.replace("%d", str(Path.home())))
        jump = resolved.get("proxyjump", "")
        result.append(
            ImportCandidate(
                alias=alias,
                host=resolved.get("hostname", alias).replace("%h", alias),
                port=port,
                user=resolved.get("user", ""),
                key_path=key_path,
                jump_host="" if jump.lower() == "none" else jump,
            )
        )
    return result
