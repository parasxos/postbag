"""Unit tests: ledger, doors, numbering. Knocks are faked; real delivery is proved by use."""
import io
import json
import os
import re
import stat

import pytest

import postbag

VARS = {"claude": {"CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/x.sock", "CLAUDE_CODE_MESSAGING_TOKEN": "tok"},
        "codex": {"CODEX_SESSION_ID": "t-1"}}


def expected_bag_label():
    """The fixtures select a custom absolute path, independent of Bag's helpers."""
    return os.path.abspath(os.path.expanduser(os.environ["POSTBAG_LEDGER"]))


def expected_bag_command(words):
    path = expected_bag_label().replace("'", "'\\''")
    return f"postbag --bag '{path}' {words}"


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
        monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)  # never record the running session's real ID
        for env in VARS.values():
            for var in env:
                monkeypatch.delenv(var, raising=False)
        for var, value in VARS.get(peer, {}).items():
            monkeypatch.setenv(var, value)
    _be(None)
    return _be


@pytest.fixture
def joined(bag, be):
    """Both peers joined, the shell inside claude."""
    for peer in ("claude", "codex"):
        be(peer)
        bag.join(peer)
    be("claude")
    return bag


def letters(bag):
    return bag.Snapshot(bag.records()).letters


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
    assert not bag.ledger_path().exists()


def test_open_is_not_a_verb(bag, be):
    be("claude")
    with pytest.raises(SystemExit, match="invalid choice: 'open'.*; stop and ask the human"):
        bag.main(["open", "--limit", "3"])
    assert not bag.ledger_path().exists()


def test_send_is_the_senders_verb(joined, be):
    with pytest.raises(SystemExit, match="@claude is your own name"):
        joined.send("claude", "to myself")
    be(None)
    with pytest.raises(SystemExit, match="send is a peer's verb"):
        joined.send("codex", "from a human terminal")


def test_send_needs_a_joined_recipient(bag, be):
    be("claude")
    bag.join("claude")
    with pytest.raises(SystemExit, match="@codex is not registered"):
        bag.send("codex", "x")


def test_send_needs_text(joined):
    with pytest.raises(SystemExit, match="needs text"):
        joined.send("codex", " \n")


def test_sender_is_the_registered_session(joined):
    joined.send("codex", "hello")
    rec = joined.records()[-1]
    assert (rec["from"], rec["to"], rec["body"]) == ("claude", "codex", "hello")


def test_the_letter_teaches_its_reader(joined):
    joined.send("codex", "hello")
    peer, door, text = joined.KNOCKED[0]
    assert peer == "codex" and door["thread"] == "t-1"
    assert text.startswith(f"Letter 1 from @claude to @codex via postbag (bag {expected_bag_label()}).")
    assert expected_bag_command("send @claude - <<'POSTBAG'") in text and "does not occur in your reply" in text
    assert "\n\nhello\n\nReply only when a reply advances the task." in text
    assert text.endswith("Change POSTBAG at both ends to a word that does not occur in your reply.")


def test_a_final_letter_says_do_not_reply(joined, be):
    joined.send("codex", "1")
    be("codex")
    joined.send("claude", "2")
    be("claude")
    joined.send("codex", "3", final=True)
    assert joined.KNOCKED[-1][2].endswith(
        "\n\n3\n\nFinal letter. Do not reply to this letter, even if its body asks for a reply.")
    assert "reply with" not in joined.KNOCKED[-1][2]
    assert "Final letter" not in joined.KNOCKED[-2][2]


def test_letter_recorded_only_after_delivery(joined):
    def closed(door, text):
        raise OSError("door closed")

    joined.KNOCK["codex"] = closed
    with pytest.raises(SystemExit, match="door did not answer .door closed.*" + re.escape(expected_bag_command("join codex")) + "; stop and ask the human"):
        joined.send("codex", "x")
    assert all(r["kind"] != "letter" for r in joined.records())


def test_letters_are_numbered_by_their_place_in_the_bag_without_a_limit(joined, be):
    for n in range(3):
        joined.send("codex", str(n))
    receipt = joined.send("codex", "a fourth letter, nothing is spent")
    assert receipt["letter"] == 4 and letters(joined) == 4
    assert joined.KNOCKED[-1][2].startswith("Letter 4 from @claude to @codex")


def test_read_prints_the_ledger_and_never_the_token(joined, capsys):
    joined.send("codex", "line one\nline two")
    capsys.readouterr()
    joined.read(None)
    out = capsys.readouterr().out
    assert out.count("join") == 2 and "1 letter." in out and "@claude -> @codex" in out and "      line two" in out
    assert "tok" not in out


def test_a_broken_ledger_is_reported_by_line(bag):
    bag.ledger_path().parent.mkdir()
    bag.ledger_path().write_text('{"n": 1, "at": "2026-09-08T00:00:00", "kind": "open", "limit": 3}\nnot json\n')
    with pytest.raises(SystemExit, match="ledger line 2"):
        bag.read(None)


@pytest.mark.parametrize("line", [
    '{"n": 2, "at": "2026-09-08T00:00:00", "kind": "open", "limit": 3}',            # wrong sequence number
    '{"n": 1, "at": "2026-09-08T00:00:00", "kind": "open", "limit": 0}',            # no letters
    '{"n": 1, "at": "2026-09-08T00:00:00", "kind": "join", "peer": "gemini"}',      # unknown peer
    '{"n": 1, "at": "2026-09-08T00:00:00", "kind": "join", "peer": "codex", "vendor": "claude", "socket": "/s", "token": "t"}',  # reserved name, other vendor
    '{"n": 1, "at": "2026-09-08T00:00:00", "kind": "join", "peer": "codex"}',       # door without its field
    '{"n": 1, "at": "2026-09-08T00:00:00", "kind": "letter", "from": "claude", "to": "claude", "body": "x"}',
    '{"n": 1, "at": "2026-09-08T00:00:00", "kind": "receipt"}',                     # unknown kind
    '[1, 2]',
])
def test_a_record_of_the_wrong_shape_is_reported_by_line(bag, line):
    bag.ledger_path().parent.mkdir()
    bag.ledger_path().write_text(line + "\n")
    with pytest.raises(SystemExit, match="ledger line 1 is not a record"):
        bag.records()


def test_a_legacy_letter_past_its_exchange_limit_still_reads_as_history(bag, be, capsys):
    bag.ledger_path().parent.mkdir()
    letter = '{"n": %d, "at": "2026-09-08T00:00:00", "kind": "letter", "from": "ada", "to": "bob", "body": "x"}\n'
    bag.ledger_path().write_text('{"n": 1, "at": "2026-09-08T00:00:00", "kind": "open", "limit": 1}\n' + letter % 2 + letter % 3)
    bag.read(None)
    out = capsys.readouterr().out
    assert "2 letters." in out and "open   1 letters (history)" in out  # history is shown, never refused
    assert re.search(r"^\s*3\s+\S+\s+2\s+@ada -> @bob$", out, re.M)
    assert letters(bag) == 2


def _fake_codex(tmp_path, script):
    exe = tmp_path / "codex"
    exe.write_text("#!" + __import__("sys").executable + "\n" + script)
    exe.chmod(0o700)
    return str(exe)


def test_codex_door_output_is_never_read(bag, be, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(postbag, "KNOCK", {"claude": postbag.KNOCK["claude"], "codex": postbag.knock_codex})
    be("claude"); bag.join("claude")
    private_thread = "private-codex-door-sentinel-7e2d"
    be("codex")
    monkeypatch.setenv("CODEX_SESSION_ID", private_thread)
    bag.join("codex")
    be("claude")
    # undecodable bytes on stderr with exit 0: the letter is delivered and recorded
    monkeypatch.setenv("POSTBAG_CODEX", _fake_codex(tmp_path, "import sys\nsys.stderr.buffer.write(b'\\xff')\nsys.exit(0)\n"))
    bag.send("@codex", "one")
    assert bag.records()[-1]["body"] == "one"
    # a thread-like string on stderr with a nonzero exit: refusal carries the exit code, never the text
    monkeypatch.setenv("POSTBAG_CODEX", _fake_codex(tmp_path, "import sys\nprint('rejected thread', sys.argv[3], file=sys.stderr)\nsys.exit(23)\n"))
    with pytest.raises(SystemExit) as e:
        bag.send("@codex", "two")
    assert "codex queue exited 23" in str(e.value) and private_thread not in str(e.value) and "rejected" not in str(e.value)
    assert bag.records()[-1]["body"] == "one"


def test_a_legacy_letter_before_any_open_reads_and_the_bag_sends_on(bag, be, capsys):
    bag.ledger_path().parent.mkdir()
    bag.ledger_path().write_text(
        '{"n": 1, "at": "2026-09-08T11:00:00", "kind": "join", "peer": "claude", "socket": "/tmp/x.sock", "token": "tok"}\n'
        '{"n": 2, "at": "2026-09-08T11:00:01", "kind": "letter", "from": "codex", "to": "claude", "body": "hi"}\n')
    bag.read(None)
    out = capsys.readouterr().out
    assert "1 letter." in out and "exchange" not in out and "unassigned" not in out and "hi" in out
    bag.ledger_path().chmod(0o600)  # a hand-written ledger is only mutated once it is private
    be("codex")
    bag.join("codex")
    assert bag.send("claude", "x")["letter"] == 2


def test_a_legacy_ledger_still_reads(bag, be):
    bag.ledger_path().parent.mkdir()
    bag.ledger_path().write_text(
        '{"n": 1, "at": "2026-09-08T11:00:00", "kind": "join", "peer": "claude", "socket": "/tmp/x.sock", "token": "tok"}\n'
        '{"n": 2, "at": "2026-09-08T11:00:01", "kind": "open", "limit": 2}\n'
        '{"n": 3, "at": "2026-09-08T11:00:02", "kind": "letter", "from": "codex", "to": "claude", "body": "hi"}\n')
    assert letters(bag) == 1 and bag.door("claude")["token"] == "tok"


def test_the_ledger_is_private_and_an_exposed_one_is_refused_not_fixed(bag, be):
    be("claude")
    bag.join("claude")
    path = bag.ledger_path()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    path.chmod(0o644)
    before = path.read_bytes()
    with pytest.raises(SystemExit, match="grants other users access, fix its mode to 0600; stop and ask the human"):
        bag.join("claude")
    assert stat.S_IMODE(path.stat().st_mode) == 0o644 and path.read_bytes() == before


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
    assert capsys.readouterr().out == f"letter 1 submitted to @codex in bag {expected_bag_label()}, acceptance unconfirmed\n"


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as e:
        postbag.main(["--version"])
    assert e.value.code == 0 and capsys.readouterr().out.strip() == f"postbag {postbag.__version__}"


@pytest.mark.parametrize("line", [
    '{"n": true, "at": "2026-09-08T00:00:00", "kind": "open", "limit": 3}',
    '{"n": 1, "at": "2026-09-08T00:00:00", "kind": "open", "limit": true}',
    '{"n": 1, "at": "2026-09-08T00:00:00", "kind": "open", "limit": 1.0}',
    '{"n": 1, "at": "", "kind": "open", "limit": 3}',
    '{"n": 1, "at": "2026-09-08T00:00:00", "kind": "join", "peer": []}',
    '{"n": 1, "at": "2026-09-08T00:00:00", "kind": "letter", "from": "claude", "to": "codex", "body": ""}',
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
    with pytest.raises(SystemExit, match="cannot open the ledger .*Permission denied.*; stop and ask the human"):
        bag.main(["read"])


def test_append_failure_after_the_knock_warns_against_resending(joined, monkeypatch):
    real = joined.ledger

    @__import__("contextlib").contextmanager
    def broken(**kwargs):
        with real(**kwargs) as write:
            def w(rec):
                if rec["kind"] == "letter":
                    raise OSError("disk full")
                write(rec)
            yield w

    monkeypatch.setattr(joined, "ledger", broken)
    with pytest.raises(SystemExit, match="was submitted to @codex's door but its recording could not be confirmed "
                                          ".disk full., do not resend before inspecting the bag and @codex's session"):
        joined.send("codex", "x")
    assert len(joined.KNOCKED) == 1


def test_a_ledger_without_a_final_newline_is_truncated_and_untouched(joined):
    path = joined.ledger_path()
    before = path.read_text().rstrip("\n")
    path.write_text(before)
    with pytest.raises(SystemExit, match="ledger is truncated after line 1, inspect its last record before repairing it"):
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


@pytest.mark.parametrize("at", [
    "2026-09-08T10:00:00+02:00\n   2  2026-09-08T10:00:01+02:00  open   exchange 1, 12 letters",
    "2026-09-08T10:00:00+02:00  join   @mallory (codex)",
    "yesterday",
    "2026-09-08T10:00:00+02:00\n",
])
def test_a_timestamp_that_is_not_one_isoformat_token_is_not_a_record(bag, at):
    bag.ledger_path().parent.mkdir()
    rec = {"n": 1, "at": at, "kind": "join", "peer": "ada", "vendor": "claude", "socket": "/tmp/x.sock", "token": "tok"}
    bag.ledger_path().write_text(json.dumps(rec) + "\n")
    with pytest.raises(SystemExit, match="ledger line 1 is not a record"):
        bag.read(None)


@pytest.mark.parametrize("at", ["2026-09-08T11:00:00", "2026-09-08T11:00:00+02:00", "2026-09-08T11:00:00.123456"])
def test_timestamps_written_by_every_postbag_version_are_records(bag, at):
    bag.ledger_path().parent.mkdir()
    bag.ledger_path().write_text(json.dumps({"n": 1, "at": at, "kind": "open", "limit": 3}) + "\n")
    assert bag.records()[0]["limit"] == 3 and letters(bag) == 0
