from easyshell.ssh import connection
from easyshell.ssh.autokey import Outcome, Probe, classify_probe, classify_push


def test_probe_classification():
    assert classify_probe(0, "") is Probe.KEY_WORKS
    assert classify_probe(255, "max@nas: Permission denied (publickey,password).") is Probe.NEEDS_PASSWORD
    # Netzwerk- oder Host-Key-Probleme sind kein Beweis für einen Passwort-Login
    assert classify_probe(255, "ssh: connect to host nas port 22: Connection refused") is Probe.UNKNOWN
    assert classify_probe(255, "Host key verification failed.") is Probe.UNKNOWN


def test_push_classification():
    assert classify_push(0, connection.KEY_ADDED + "\n") is Outcome.ADDED
    assert classify_push(0, connection.KEY_PRESENT + "\n") is Outcome.ALREADY_PRESENT
    assert classify_push(255, "") is Outcome.FAILED
