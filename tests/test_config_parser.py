from pathlib import Path

from patchbay.ssh.config_parser import parse_ssh_config

CONFIG = """
# globale Option vor dem ersten Host
User fallback

Host nas
    HostName 192.168.1.20
    Port=2222
    IdentityFile ~/.ssh/id_nas

Host pihole pi
  hostname "pihole.lan"
  ProxyJump nas

Host *.intern !secret.intern
  User admin

Host secret.intern

Match host foo
  User nie

Include conf.d/*.conf

Host *
  User letzter
  Port 22
"""


def write(tmp_path: Path) -> Path:
    ssh = tmp_path / ".ssh"
    (ssh / "conf.d").mkdir(parents=True)
    (ssh / "config").write_text(CONFIG)
    (ssh / "conf.d" / "spiele.conf").write_text("Host gameserver\n  HostName 10.0.0.5\n  User steam\n")
    return ssh / "config"


def by_alias(tmp_path):
    return {c.alias: c for c in parse_ssh_config(write(tmp_path))}


def test_concrete_aliases_only(tmp_path):
    assert list(by_alias(tmp_path)) == ["nas", "pihole", "pi", "secret.intern", "gameserver"]


def test_first_value_wins_and_equals_syntax(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    nas = by_alias(tmp_path)["nas"]
    assert nas.host == "192.168.1.20"
    assert nas.port == 2222
    assert nas.user == "fallback"  # globale Option steht vor "Host *"
    assert nas.key_path == str(tmp_path / ".ssh" / "id_nas")


def test_multiple_patterns_quotes_and_proxyjump(tmp_path):
    hosts = by_alias(tmp_path)
    assert hosts["pihole"].host == "pihole.lan"
    assert hosts["pi"].host == "pihole.lan"
    assert hosts["pi"].jump_host == "nas"


def test_negation_and_match_blocks_ignored(tmp_path):
    secret = by_alias(tmp_path)["secret.intern"]
    assert secret.host == "secret.intern"
    assert secret.user == "fallback"  # nicht "admin" (negiert), nicht "nie" (Match)


def test_include_relative_to_ssh_dir(tmp_path):
    game = by_alias(tmp_path)["gameserver"]
    # wie bei ssh: die globale Option ganz oben gewinnt auch gegen den Include
    assert (game.host, game.user, game.port) == ("10.0.0.5", "fallback", 22)


def test_missing_file(tmp_path):
    assert parse_ssh_config(tmp_path / "gibtsnicht") == []
