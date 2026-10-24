from patchbay.models import Server
from patchbay.ssh import connection
from patchbay.ssh.connection import command_string, copy_id_argv, parse_quick_target


def test_command_string_with_jump_by_name(monkeypatch):
    bastion = Server(name="bastion", host="1.2.3.4", user="max", port=2200)
    target = Server(name="nas", host="10.0.0.2", user="root", key_path="/k/id", jump_host="bastion")
    cmd = command_string(target, lambda n: bastion if n == "bastion" else None)
    assert cmd == "ssh -i /k/id -o IdentitiesOnly=yes -J max@1.2.3.4:2200 root@10.0.0.2"


def test_copy_id_quotes_key(monkeypatch):
    monkeypatch.setattr(connection, "host_prefix", lambda p="ssh": ["ssh"])
    argv = copy_id_argv(Server(name="a", host="h"), "ssh-ed25519 AAAA max@pc")
    assert argv[:2] == ["ssh", "h"]
    assert "'ssh-ed25519 AAAA max@pc'" in argv[-1]


def test_quick_target():
    s = parse_quick_target("root@[fe80::1]:2222")
    assert (s.user, s.host, s.port) == ("root", "fe80::1", 2222)
    assert parse_quick_target("ssh pi.lan").host == "pi.lan"
    assert parse_quick_target("a b") is None
