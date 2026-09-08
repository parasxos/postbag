"""Unit tests: ledger, doors, budget. Knocks are faked; real delivery is proved by use."""
import io
import types
from pathlib import Path

import pytest

SRC = Path(__file__).with_name("postbag").read_text()
VARS = {"claude": {"CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/x.sock", "CLAUDE_CODE_MESSAGING_TOKEN": "tok"},
        "codex": {"CODEX_SESSION_ID": "t-1"}}


@pytest.fixture
def postbag(tmp_path, monkeypatch):
    monkeypatch.setenv("POSTBAG_LEDGER", str(tmp_path / "ledger.jsonl"))
    mod = types.ModuleType("postbag")
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
def joined(postbag, be):
    """Both peers joined, an exchange of 3 open, the shell inside claude."""
    for peer in ("claude", "codex"):
        be(peer)
        postbag.join(peer)
    be(None)
    postbag.open_exchange(3)
    be("claude")
    return postbag


def test_join_publishes_the_door_in_the_ledger(joined):
    d = joined.door("claude")
    assert (d["kind"], d["peer"], d["socket"], d["token"]) == ("join", "claude", "/tmp/x.sock", "tok")
    assert joined.door("codex")["thread"] == "t-1"


def test_join_only_from_inside_its_own_session(postbag, be):
    with pytest.raises(SystemExit, match="inside a claude session"):
        postbag.join("claude")
    be("codex")
    with pytest.raises(SystemExit, match="inside a claude session"):
        postbag.join("claude")


def test_open_is_the_humans_verb(postbag, be):
    be("claude")
    with pytest.raises(SystemExit, match="human"):
        postbag.open_exchange(3)


def test_send_is_the_senders_verb(joined, be):
    with pytest.raises(SystemExit, match="codex's verb"):
        joined.send("claude", "to myself")
    be(None)
    with pytest.raises(SystemExit, match="claude's verb"):
        joined.send("codex", "from a human terminal")


def test_send_needs_an_open_exchange(postbag, be):
    be("claude")
    postbag.join("claude")
    with pytest.raises(SystemExit, match="no exchange is open"):
        postbag.send("codex", "x")


def test_send_needs_a_joined_recipient(postbag, be):
    postbag.open_exchange(3)
    be("claude")
    with pytest.raises(SystemExit, match="codex has not joined"):
        postbag.send("codex", "x")


def test_send_needs_text(joined):
    with pytest.raises(SystemExit, match="needs text"):
        joined.send("codex", " \n")


def test_sender_is_the_other_peer(joined):
    joined.send("codex", "hello")
    rec = joined.records()[-1]
    assert (rec["from"], rec["to"], rec["body"]) == ("claude", "codex", "hello")


def test_the_letter_teaches_its_reader(joined):
    joined.send("codex", "hello")
    peer, door, text = joined.KNOCKED[0]
    assert peer == "codex" and door["thread"] == "t-1"
    assert text.startswith("Letter 4 from claude via postbag. If it needs an answer")
    assert "postbag send claude - <<'letter'" in text and text.endswith("Otherwise do nothing.\n\nhello")


def test_the_last_letter_says_do_not_reply(joined, be):
    joined.send("codex", "1")
    be("codex")
    joined.send("claude", "2")
    be("claude")
    joined.send("codex", "3")
    assert "last letter of the exchange; do not reply" in joined.KNOCKED[-1][2]
    assert "reply with" not in joined.KNOCKED[-1][2]


def test_letter_recorded_only_after_delivery(joined):
    def closed(door, text):
        raise OSError("door closed")

    joined.KNOCK["codex"] = closed
    with pytest.raises(SystemExit, match="door did not answer .door closed.; stop"):
        joined.send("codex", "x")
    assert all(r["kind"] != "letter" for r in joined.records())


def test_budget_is_the_one_recorded_at_open(joined, be):
    for n in range(3):
        joined.send("codex", str(n))
    with pytest.raises(SystemExit, match="spent; stop"):
        joined.send("codex", "one too many")
    be(None)
    joined.open_exchange(1)
    be("claude")
    joined.send("codex", "fine")
    assert joined.budget() == 0


def test_read_prints_the_ledger_and_never_the_token(joined, capsys):
    joined.send("codex", "line one\nline two")
    capsys.readouterr()
    joined.read(None)
    out = capsys.readouterr().out
    assert out.count("join") == 2 and "3 letters" in out and "claude -> codex" in out and "      line two" in out
    assert "tok" not in out


def test_a_broken_ledger_is_reported_by_line(postbag, be):
    postbag.LEDGER.parent.mkdir(exist_ok=True)
    postbag.LEDGER.write_text('{"n": 1, "kind": "open", "limit": 3}\nnot json\n')
    with pytest.raises(SystemExit, match="ledger line 2"):
        postbag.read(None)


def test_cli_send_reads_stdin_including_an_eof_line(joined, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("cat <<'EOF'\nhi\nEOF\n"))
    joined.main(["send", "codex", "-"])
    assert joined.records()[-1]["body"] == "cat <<'EOF'\nhi\nEOF"
    assert "2 left" in capsys.readouterr().out
