"""Unit tests: ledger, doors, budget. Knocks are faked; real delivery is proved by use."""
import io
import json
import os
import stat

import pytest

import postbag

VARS = {"claude": {"CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/x.sock", "CLAUDE_CODE_MESSAGING_TOKEN": "tok"},
        "codex": {"CODEX_SESSION_ID": "t-1"}}


@pytest.fixture
def bag(tmp_path, monkeypatch):
    monkeypatch.setenv("POSTBAG_LEDGER", str(tmp_path / "state" / "ledger.jsonl"))
    knocked = []
    monkeypatch.setattr(postbag, "KNOCK", {p: (lambda d, t, p=p: knocked.append((p, d, t))) for p in postbag.PEERS})
    postbag.KNOCKED = knocked
    return postbag


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
def joined(bag, be):
    """Both peers joined, an exchange of 3 open, the shell inside claude."""
    for peer in ("claude", "codex"):
        be(peer)
        bag.join(peer)
    be(None)
    bag.open_exchange(3)
    be("claude")
    return bag


def test_join_publishes_the_door_in_the_ledger(joined):
    d = joined.door("claude")
    assert (d["kind"], d["peer"], d["socket"], d["token"]) == ("join", "claude", "/tmp/x.sock", "tok")
    assert joined.door("codex")["thread"] == "t-1"


def test_join_only_from_inside_its_own_session(bag, be):
    with pytest.raises(SystemExit, match="inside a claude session"):
        bag.join("claude")
    be("codex")
    with pytest.raises(SystemExit, match="inside a claude session"):
        bag.join("claude")


def test_open_is_the_humans_verb(bag, be):
    be("claude")
    with pytest.raises(SystemExit, match="human"):
        bag.open_exchange(3)


def test_send_is_the_senders_verb(joined, be):
    with pytest.raises(SystemExit, match="codex's verb"):
        joined.send("claude", "to myself")
    be(None)
    with pytest.raises(SystemExit, match="claude's verb"):
        joined.send("codex", "from a human terminal")


def test_send_needs_an_open_exchange(bag, be):
    be("claude")
    bag.join("claude")
    with pytest.raises(SystemExit, match="no exchange is open"):
        bag.send("codex", "x")


def test_send_needs_a_joined_recipient(bag, be):
    bag.open_exchange(3)
    be("claude")
    with pytest.raises(SystemExit, match="codex has not joined"):
        bag.send("codex", "x")


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
    assert "postbag send claude - <<'POSTBAG'" in text and "does not occur in your reply" in text
    assert text.endswith("Otherwise do nothing.\n\nhello")


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
    with pytest.raises(SystemExit, match="door did not answer .door closed.*postbag join codex; stop and ask the human"):
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


def test_a_broken_ledger_is_reported_by_line(bag):
    bag.ledger_path().parent.mkdir()
    bag.ledger_path().write_text('{"n": 1, "at": "x", "kind": "open", "limit": 3}\nnot json\n')
    with pytest.raises(SystemExit, match="ledger line 2"):
        bag.read(None)


@pytest.mark.parametrize("line", [
    '{"n": 2, "at": "x", "kind": "open", "limit": 3}',            # wrong sequence number
    '{"n": 1, "at": "x", "kind": "open", "limit": 0}',            # no letters
    '{"n": 1, "at": "x", "kind": "join", "peer": "gemini"}',      # unknown peer
    '{"n": 1, "at": "x", "kind": "join", "peer": "codex"}',       # door without its field
    '{"n": 1, "at": "x", "kind": "letter", "from": "claude", "to": "claude", "body": "x"}',
    '{"n": 1, "at": "x", "kind": "receipt"}',                     # unknown kind
    '[1, 2]',
])
def test_a_record_of_the_wrong_shape_is_reported_by_line(bag, line):
    bag.ledger_path().parent.mkdir()
    bag.ledger_path().write_text(line + "\n")
    with pytest.raises(SystemExit, match="ledger line 1 is not a record"):
        bag.records()


def test_a_legacy_ledger_still_reads(bag, be):
    bag.ledger_path().parent.mkdir()
    bag.ledger_path().write_text(
        '{"n": 1, "at": "2026-09-08T11:00:00", "kind": "join", "peer": "claude", "socket": "/tmp/x.sock", "token": "tok"}\n'
        '{"n": 2, "at": "2026-09-08T11:00:01", "kind": "open", "limit": 2}\n'
        '{"n": 3, "at": "2026-09-08T11:00:02", "kind": "letter", "from": "codex", "to": "claude", "body": "hi"}\n')
    assert bag.budget() == 1 and bag.door("claude")["token"] == "tok"


def test_the_ledger_is_private(bag, be):
    be("claude")
    bag.join("claude")
    path = bag.ledger_path()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    path.chmod(0o644)
    bag.join("claude")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_records_carry_a_utc_offset(joined):
    at = joined.records()[-1]["at"]
    assert at[-6] in "+-" and at[-3] == ":"


def test_codex_path_prefers_the_override(monkeypatch):
    monkeypatch.setenv("POSTBAG_CODEX", "/x/codex")
    assert postbag.codex_path() == "/x/codex"
    monkeypatch.delenv("POSTBAG_CODEX")
    assert postbag.codex_path() in (postbag.MACOS_CODEX, "codex") or os.path.isabs(postbag.codex_path())


def test_cli_send_reads_stdin_including_an_eof_line(joined, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("cat <<'EOF'\nhi\nEOF\n"))
    joined.main(["send", "codex", "-"])
    assert joined.records()[-1]["body"] == "cat <<'EOF'\nhi\nEOF"
    assert "2 left" in capsys.readouterr().out


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as e:
        postbag.main(["--version"])
    assert e.value.code == 0 and capsys.readouterr().out.strip() == f"postbag {postbag.__version__}"


@pytest.mark.parametrize("line", [
    '{"n": true, "at": "x", "kind": "open", "limit": 3}',
    '{"n": 1, "at": "x", "kind": "open", "limit": true}',
    '{"n": 1, "at": "x", "kind": "open", "limit": 1.0}',
    '{"n": 1, "at": "", "kind": "open", "limit": 3}',
    '{"n": 1, "at": "x", "kind": "join", "peer": []}',
    '{"n": 1, "at": "x", "kind": "letter", "from": "claude", "to": "codex", "body": ""}',
])
def test_a_record_of_the_wrong_type_is_reported_by_line(bag, line):
    bag.ledger_path().parent.mkdir()
    bag.ledger_path().write_text(line + "\n")
    with pytest.raises(SystemExit, match="ledger line 1 is not a record"):
        bag.records()


def test_the_ledger_must_be_a_regular_file(bag, be, tmp_path):
    os.mkfifo(tmp_path / "fifo")
    bag.ledger_path().parent.mkdir()
    os.symlink(tmp_path / "fifo", bag.ledger_path())
    be("claude")
    with pytest.raises(SystemExit, match="cannot open the ledger"):
        bag.join("claude")


def test_an_unreadable_ledger_is_a_refusal_not_a_traceback(bag, be, capsys):
    be("claude")
    bag.join("claude")
    bag.ledger_path().chmod(0)
    with pytest.raises(SystemExit, match="read failed"):
        bag.main(["read"])


def test_append_failure_after_the_knock_warns_against_resending(joined, monkeypatch):
    real = joined.ledger

    @__import__("contextlib").contextmanager
    def broken():
        with real() as write:
            def w(rec):
                if rec["kind"] == "letter":
                    raise OSError("disk full")
                write(rec)
            yield w

    monkeypatch.setattr(joined, "ledger", broken)
    with pytest.raises(SystemExit, match="was submitted to codex's door but not recorded .disk full.; do not resend"):
        joined.send("codex", "x")
    assert len(joined.KNOCKED) == 1


def test_a_ledger_without_a_final_newline_is_truncated_and_untouched(joined):
    path = joined.ledger_path()
    before = path.read_text().rstrip("\n")
    path.write_text(before)
    with pytest.raises(SystemExit, match="ledger is truncated after line 2"):
        joined.send("codex", "x")
    assert joined.KNOCKED == [] and path.read_text() == before


def test_cli_read_refuses_a_fifo_instead_of_hanging(bag, tmp_path):
    bag.ledger_path().parent.mkdir()
    os.mkfifo(bag.ledger_path())
    with pytest.raises(SystemExit, match="not a regular file"):
        bag.main(["read"])


def test_cli_read_refuses_a_symlinked_ledger(bag, tmp_path):
    bag.ledger_path().parent.mkdir()
    (tmp_path / "real.jsonl").write_text("")
    os.symlink(tmp_path / "real.jsonl", bag.ledger_path())
    with pytest.raises(SystemExit, match="cannot open the ledger"):
        bag.main(["read"])
