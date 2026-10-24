import json
import stat

from patchbay.models import Server
from patchbay.storage import ServerStore


def make_store(tmp_path):
    store = ServerStore(tmp_path / "patchbay" / "servers.json")
    store.load()
    return store


def test_missing_file_gives_empty_store(tmp_path):
    store = make_store(tmp_path)
    assert store.servers == []
    assert store.load_warning is None


def test_roundtrip_and_permissions(tmp_path):
    store = make_store(tmp_path)
    store.upsert(Server(name="NAS", host="192.168.1.20", user="max", group="Keller", color="yellow"))
    mode = stat.S_IMODE(store.path.stat().st_mode)
    assert mode == 0o600

    again = make_store(tmp_path)
    assert [s.name for s in again.servers] == ["NAS"]
    assert again.servers[0].color == "yellow"
    assert again.servers[0].address == "max@192.168.1.20"


def test_never_stores_passwords(tmp_path):
    store = make_store(tmp_path)
    store.path.parent.mkdir(parents=True)
    store.path.write_text(json.dumps({"servers": [{"name": "a", "host": "h", "password": "geheim"}]}))
    store.load()
    store.save()
    assert "geheim" not in store.path.read_text()


def test_update_duplicate_remove(tmp_path):
    store = make_store(tmp_path)
    server = Server(name="Pi-hole", host="pihole.lan", port=2222)
    store.upsert(server)
    server.notes = "DNS"
    store.upsert(server)
    assert len(store.servers) == 1

    copy = store.duplicate(server.id)
    assert copy.id != server.id
    assert copy.name == "Pi-hole (Kopie)"
    assert copy.port == 2222
    assert store.servers.index(copy) == 1

    store.remove(server.id)
    assert [s.id for s in make_store(tmp_path).servers] == [copy.id]


def test_corrupt_file_is_backed_up(tmp_path):
    path = tmp_path / "patchbay" / "servers.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ kaputt")
    store = ServerStore(path)
    store.load()
    assert store.servers == []
    assert "nicht lesbar" in store.load_warning
    assert list(path.parent.glob("servers.json.defekt-*"))


def test_invalid_entries_are_skipped_and_values_cleaned(tmp_path):
    path = tmp_path / "servers.json"
    path.write_text(json.dumps({"servers": [
        {"name": "ok", "host": "h", "port": "99999", "color": "orange", "unknown": 1},
        {"name": "", "host": "h"},
        "kein objekt",
    ]}))
    store = ServerStore(path)
    store.load()
    assert len(store.servers) == 1
    assert store.servers[0].port == 22
    assert store.servers[0].color == "blue"
    assert "2 Einträge" in store.load_warning


def test_recent_and_group_color(tmp_path):
    store = make_store(tmp_path)
    a = Server(name="a", host="a", group="Spiele", color="green")
    b = Server(name="b", host="b", group="Spiele", color="green")
    c = Server(name="c", host="c", group="Spiele", color="red")
    for s in (a, b, c):
        store.upsert(s)
    store.mark_connected(c.id)
    assert [s.name for s in store.recent()] == ["c"]
    assert store.color_for_group("Spiele") == "green"
    assert store.groups() == ["Spiele"]
