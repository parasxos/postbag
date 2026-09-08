"""Unit tests: ledger, doors, budget. Knocks are faked; real delivery is proved by use."""
import io
import types
from pathlib import Path

import pytest

SRC = Path(__file__).with_name("bridge").read_text()
VARS = {"claude": {"CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/x.sock", "CLAUDE_CODE_MESSAGING_TOKEN": "tok"},
        "codex": {"CODEX_SESSION_ID": "t-1"}}


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIDGE_LEDGER", str(tmp_path / "ledger.jsonl"))
    mod = types.ModuleType("bridge")
    exec(SRC, mod.__dict__)  # the script has no .py suffix and binds LEDGER at import
    mod.KNOCKED = []
    mod.KNOCK = {peer: (lambda d, t, peer=peer: mod.KNOCKED.append((peer, d, t))) for peer in mod.PEERS}
    return mod


@pytest.fixture
def be(monkeypatch):
    """be("claude") puts the shell inside that session; be(None) makes it a human's terminal."""
    def _be(peer):
        for env in VARS.values():
            for var in env:
                monkeypatch.delenv(var, raising=False)
        for var, value in VARS.get(peer, {}).items():
            monkeypatch.setenv(var, value)
    _be(None)
    return _be


@pytest.fixture
def joined(bridge, be):
    for peer in ("claude", "codex"):
        be(peer)
        bridge.join(peer)
    be(None)
    return bridge


def test_join_publishes_the_door_in_the_ledger(joined):
    d = joined.door("claude")
    assert (d["kind"], d["peer"], d["socket"], d["token"]) == ("join", "claude", "/tmp/x.sock", "tok")
    assert joined.door("codex")["thread"] == "t-1"


def test_join_only_from_inside_its_own_session(bridge, be):
    with pytest.raises(SystemExit, match="inside a claude session"):
        bridge.join("claude")
    be("codex")
    with pytest.raises(SystemExit, match="inside a claude session"):
        bridge.join("claude")


def test_open_is_the_humans_verb(bridge, be):
    be("claude")
    with pytest.raises(SystemExit, match="human"):
        bridge.open_exchange(3)


def test_send_needs_an_open_exchange(joined):
    with pytest.raises(SystemExit, match="no exchange is open"):
        joined.send("codex", "x")


def test_sender_is_the_other_peer(joined):
    joined.open_exchange(3)
    joined.send("codex", "hello")
    rec = joined.records()[-1]
    assert (rec["from"], rec["to"], rec["body"]) == ("claude", "codex", "hello")


def test_the_letter_teaches_its_reader(joined):
    joined.open_exchange(3)
    joined.send("codex", "hello")
    peer, door, text = joined.KNOCKED[0]
    assert peer == "codex" and door["thread"] == "t-1"
    assert text.startswith("Letter 4 from claude") and "bridge send claude - <<'EOF'" in text and text.endswith("\n\nhello")


def test_letter_recorded_only_after_delivery(joined):
    joined.open_exchange(3)

    def closed(door, text):
        raise OSError("door closed")

    joined.KNOCK["claude"] = closed
    with pytest.raises(SystemExit, match="door did not answer"):
        joined.send("claude", "x")
    assert all(r["kind"] != "letter" for r in joined.records())


def test_budget_is_the_one_recorded_at_open(joined):
    joined.open_exchange(2)
    joined.send("codex", "1")
    joined.send("claude", "2")
    with pytest.raises(SystemExit, match="spent; stop"):
        joined.send("codex", "3")
    joined.open_exchange(1)
    joined.send("codex", "fine")
    assert joined.budget() == 0


def test_read_prints_the_ledger_and_never_the_token(joined, capsys):
    joined.open_exchange(3)
    joined.send("codex", "line one\nline two")
    capsys.readouterr()
    joined.read(None)
    out = capsys.readouterr().out
    assert out.count("join") == 2 and "3 letters" in out and "claude -> codex" in out and "      line two" in out
    assert "tok" not in out


def test_cli_send_reads_stdin(joined, monkeypatch, capsys):
    joined.open_exchange(3)
    monkeypatch.setattr("sys.stdin", io.StringIO("from stdin\n"))
    joined.main(["send", "claude", "-"])
    assert joined.records()[-1]["body"] == "from stdin"
    assert "2 left" in capsys.readouterr().out
