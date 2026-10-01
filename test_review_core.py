"""Review fixes in the core: recovery metadata, input validity, recording wording, ledger parsing, envelope."""
import fcntl
import json
import os
import subprocess
import sys

import pytest

import postbag
from test_hardening import SCRIPT, cli, fake_codex, prepare_exchange  # noqa: F401 -- subprocess fixture with a private ledger
from test_names import session  # noqa: F401
from test_postbag import bag, be, joined, expected_bag_command, expected_bag_label  # noqa: F401


def refusal(operation):
    with pytest.raises(postbag.Refusal) as error:
        operation()
    return error.value


# recovery metadata ------------------------------------------------------------

def test_a_refusal_carries_no_recovery_by_default(joined):
    error = refusal(lambda: joined.send("codex", " \n"))
    assert error.recovery is None
    assert postbag.Refusal("x").recovery is None


def test_unjoined_sender_recovery_names_the_one_vendor(bag, be):
    be("codex")
    bag.join("codex")
    be(None)
    bag.open_exchange(3)
    be("claude")
    error = refusal(lambda: bag.send("codex", "not joined"))
    assert "this session has not joined" in str(error)
    assert error.recovery == {"action": "join", "actor": "caller", "bag": expected_bag_label(),
                              "vendor": "claude", "name": None}


def test_unjoined_sender_inside_two_vendors_leaves_the_vendor_open(bag, session, monkeypatch):
    session("claude", "two")
    bag.join("claude", "bob")
    session()
    bag.open_exchange(3)
    session("codex", "one")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_SOCKET", "/tmp/postbag-test-nine.sock")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_TOKEN", "fake-token-nine")
    error = refusal(lambda: bag.send("bob", "unjoined in two sessions"))
    assert error.recovery == {"action": "join", "actor": "caller", "bag": expected_bag_label(),
                              "vendor": None, "name": None}


def test_lost_name_recovery_is_a_rejoin(bag, session):
    session("codex", "one")
    bag.join("codex", "ada")
    session("claude", "two")
    bag.join("claude", "bob")
    session("codex", "three")
    bag.join("codex", "ada")  # took ada from door one
    session()
    bag.open_exchange(3)
    session("codex", "one")
    error = refusal(lambda: bag.send("bob", "displaced"))
    assert "your name @ada was taken" in str(error)
    assert error.recovery == {"action": "join", "actor": "caller", "bag": expected_bag_label(),
                              "vendor": "codex", "name": None}


def test_unknown_target_recovery_is_a_read(joined):
    error = refusal(lambda: joined.send("nobody", "to an unknown name"))
    assert "@nobody is not registered" in str(error)
    assert error.recovery == {"action": "read", "actor": "caller", "bag": expected_bag_label()}
    assert refusal(lambda: joined.door("nobody")).recovery == error.recovery


@pytest.mark.parametrize("named", [False, True], ids=["vendor-name", "custom-name"])
def test_silent_door_recovery_tells_the_recipient_to_rejoin(bag, be, named):
    to = "bob" if named else "codex"
    be("codex")
    bag.join("codex", to)
    be("claude")
    bag.join("claude")
    be(None)
    bag.open_exchange(3)
    be("claude")

    def closed(door, text):
        raise OSError("door closed")

    bag.KNOCK["codex"] = closed
    error = refusal(lambda: bag.send(to, "nobody home"))
    assert error.error_code == "transport_unavailable"
    assert error.recovery == {"action": "join", "actor": "recipient", "bag": expected_bag_label(),
                              "vendor": "codex", "name": to}


def test_no_exchange_and_spent_exchange_recovery_is_a_human_open(bag, be):
    be("claude")
    bag.join("claude")
    be("codex")
    bag.join("codex")
    reopen = {"action": "open", "actor": "human", "bag": expected_bag_label()}
    assert refusal(lambda: bag.send("claude", "before any open")).recovery == reopen
    be(None)
    bag.open_exchange(1)
    be("codex")
    bag.send("claude", "the only letter")
    error = refusal(lambda: bag.send("claude", "one too many"))
    assert "spent" in str(error) and error.recovery == reopen


def test_missing_named_bag_recovery_is_a_human_open(bag, be, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    be("claude")
    error = refusal(lambda: bag.main(["--bag", "acceptance", "join", "claude"]))
    assert "bag acceptance does not exist" in str(error)
    assert error.recovery == {"action": "open", "actor": "human", "bag": "acceptance"}
    assert not (tmp_path / ".postbag").exists()


def test_busy_ledger_recovery_is_a_read_and_says_so(joined):
    with joined.ledger_path().open("r+") as holder:
        fcntl.flock(holder, fcntl.LOCK_EX)
        error = refusal(lambda: joined.send("codex", "while busy", wait=False))
    assert error.error_code == "ledger_busy"
    assert "the ledger is busy, read the bag before doing anything else" in str(error)
    assert error.recovery == {"action": "read", "actor": "caller", "bag": expected_bag_label()}
    assert joined.KNOCKED == []


# input validity ---------------------------------------------------------------

def test_a_body_that_is_not_unicode_text_is_refused_before_the_lock(joined):
    before = joined.ledger_path().read_bytes()
    with joined.ledger_path().open("r+") as holder:
        fcntl.flock(holder, fcntl.LOCK_EX)  # a held lock proves the refusal comes first
        error = refusal(lambda: joined.send("codex", "a\udcffb", wait=False))
    assert error.error_code == "invalid_input" and error.submission_state == "not_submitted"
    assert "a letter must be valid Unicode text" in str(error)
    assert joined.KNOCKED == []
    assert joined.ledger_path().read_bytes() == before


def test_a_legacy_ledger_with_a_surrogate_body_still_reads_inventories_joins_and_sends(bag, be, cli, tmp_path, monkeypatch):
    """History written by an older postbag under a C locale: json escaped the surrogate, so the file is UTF-8."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    bag.ledger_path().parent.mkdir()
    rows = [{"n": 1, "at": "2026-09-08T00:00:00", "kind": "open", "limit": 3},
            {"n": 2, "at": "2026-09-08T00:00:01", "kind": "letter", "from": "ada", "to": "bob", "body": "a\udcffb"}]
    original = "".join(json.dumps(row) + "\n" for row in rows)
    bag.ledger_path().write_text(original, encoding="utf-8")
    assert [rec["body"] for rec in bag.records() if rec["kind"] == "letter"] == ["a\udcffb"]
    assert bag.budget() == 2
    listed, counts, _, problems = bag.inventory()
    assert problems == [] and counts["remaining"] == 1
    assert listed[-1][:2] == (expected_bag_label(), "2/3")
    be("codex")
    bag.join("codex")
    be("claude")
    bag.join("claude")
    bag.send("codex", "a new letter after the legacy one")
    assert len(bag.KNOCKED) == 1 and bag.records()[-1]["body"] == "a new letter after the legacy one"
    assert bag.ledger_path().read_text(encoding="utf-8").startswith(original)
    # The CLI display of that one body is contained as before: a refusal, not a traceback, and no body text.
    cli.ledger.write_text(original, encoding="utf-8")  # the same tmp ledger, back to the legacy history
    shown = cli("read", extra={"PYTHONIOENCODING": "utf-8"})
    assert shown.returncode == 1 and "read failed" in shown.stderr and "Traceback" not in shown.stderr


def test_cli_stdin_with_undecodable_bytes_is_refused_before_any_door(cli, fake_codex):
    sender, recipient, extra = prepare_exchange(cli, 1)
    before = cli.ledger.read_bytes()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "send", recipient, "-"],
        env=cli.environment(sender, {**fake_codex, **extra, "PYTHONIOENCODING": "utf-8:surrogateescape"}),
        input=b"hello \xff world", capture_output=True, timeout=10,
    )
    assert result.returncode == 1
    assert b"a letter must be valid Unicode text" in result.stderr and b"stop and ask the human" in result.stderr
    assert b"Traceback" not in result.stderr
    assert not os.path.exists(fake_codex["POSTBAG_TEST_CAPTURE"])
    assert cli.ledger.read_bytes() == before


def test_a_send_that_fails_before_the_record_is_written_leaves_no_record(joined, monkeypatch):
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
    error = refusal(lambda: joined.send("codex", "never landed"))
    assert error.error_code == "recording_failed" and error.submission_state == "submitted"
    assert "recording could not be confirmed (disk full)" in str(error) and "inspecting the bag" in str(error)
    assert len(joined.KNOCKED) == 1
    assert all(rec["kind"] != "letter" for rec in joined.records())


# recording after submission ---------------------------------------------------

def test_fsync_failure_after_the_record_landed_says_to_inspect_the_bag(joined, monkeypatch):
    before = joined.records()
    assert joined.budget() == 3

    def unsynced(fd):
        raise OSError("fsync refused")

    monkeypatch.setattr(postbag.os, "fsync", unsynced)
    error = refusal(lambda: joined.send("codex", "durability unknown"))
    assert error.error_code == "recording_failed" and error.submission_state == "submitted"
    message = str(error)
    assert "recording could not be confirmed (fsync refused)" in message
    assert "inspecting the bag" in message and "do not resend" in message
    assert "not recorded" not in message
    assert len(joined.KNOCKED) == 1  # exactly one native side effect
    after = joined.records()
    assert after[:-1] == before and len(after) == len(before) + 1  # exactly one new record
    assert after[-1]["kind"] == "letter" and after[-1]["body"] == "durability unknown"
    assert joined.budget() == 2  # exactly one budget slot consumed


# ledger parsing ---------------------------------------------------------------

def test_an_integer_past_the_digit_limit_is_not_a_record(bag):
    """The huge value sits in limit, a field shape validation accepts, so only the digit limit can refuse it."""
    if not hasattr(sys, "set_int_max_str_digits"):
        pytest.skip("this Python has no integer digit limit")
    bag.ledger_path().parent.mkdir()
    bag.ledger_path().write_text('{"n": 1, "at": "2026-09-08T00:00:00", "kind": "open", "limit": ' + "9" * 700 + '}\n')
    previous = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(640)
    try:
        with pytest.raises(postbag.Refusal, match="ledger line 1 is not a record"):
            bag.records()
        sys.set_int_max_str_digits(0)  # with the limit off, the same line is an ordinary record
        assert bag.budget() == int("9" * 700)
    finally:
        sys.set_int_max_str_digits(previous)


def test_cli_read_of_an_integer_past_the_digit_limit_is_a_refusal_not_a_traceback(cli):
    cli.ledger.parent.mkdir()
    cli.ledger.write_text('{"n": 1, "at": "2026-09-08T00:00:00", "kind": "open", "limit": ' + "9" * 700 + '}\n')
    result = cli("read", extra={"PYTHONINTMAXSTRDIGITS": "640"})
    assert result.returncode == 1
    assert "ledger line 1 is not a record" in result.stderr and "stop and ask the human" in result.stderr
    assert "Traceback" not in result.stderr


# envelope -----------------------------------------------------------------------

HEREDOC_TAIL = ("<your reply>\nPOSTBAG\n"
                "Change POSTBAG at both ends to a word that does not occur in your reply.\n"
                "Do not reply only to acknowledge.")


@pytest.mark.parametrize("label", ["default", "acceptance"])
def test_the_envelope_offers_the_mcp_tool_for_a_named_or_default_bag(bag, be, tmp_path, monkeypatch, label):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("POSTBAG_LEDGER")
    select = [] if label == "default" else ["--bag", label]
    bag.main([*select, "open", "--limit", "3"])
    be("codex")
    bag.main([*select, "join", "codex"])
    be("claude")
    bag.main([*select, "join", "claude"])
    bag.main([*select, "send", "codex", "hello"])
    text = bag.KNOCKED[0][2]
    assert f"(exchange 1, bag {label})." in text
    assert text.endswith(
        "\n\nhello\n\n"
        f"If it needs an answer and you have Postbag MCP tools, call postbag_send with bag {label} and to @claude.\n"
        "Otherwise reply with:\n"
        f"postbag --bag {label} send @claude - <<'POSTBAG'\n" + HEREDOC_TAIL
    )


def test_the_envelope_for_a_path_bag_keeps_the_shell_reply_only(joined):
    joined.send("codex", "hello")
    text = joined.KNOCKED[0][2]
    assert "postbag_send" not in text and "MCP" not in text
    assert text.endswith(
        "\n\nhello\n\nIf it needs an answer, reply with:\n"
        f"{expected_bag_command('send @claude -')} <<'POSTBAG'\n" + HEREDOC_TAIL
    )


# codex child environment ------------------------------------------------------

def test_codex_child_never_inherits_door_fields_or_the_ledger_selection(joined, be, tmp_path, monkeypatch):
    dump = tmp_path / "child-environment.json"
    exe = tmp_path / "fake-codex"
    exe.write_text(f"#!{os.sys.executable}\nimport json, os\n"
                   f"json.dump(dict(os.environ), open({str(dump)!r}, 'w'))\n")
    exe.chmod(0o700)
    monkeypatch.setenv("POSTBAG_CODEX", str(exe))
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "11111111-2222-3333-4444-555555555555")
    monkeypatch.setenv("CODEX_THREAD_ID", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    # The fake process dumps its environment: include only deliberate fixture values.
    environment = {key: os.environ[key] for key in postbag.HIDDEN_FROM_CHILD if key in os.environ}
    environment.update(HOME=str(tmp_path), PATH=os.defpath, POSTBAG_CODEX=str(exe),
                       CODEX_HOME=str(tmp_path / "runtime-home"))
    monkeypatch.setattr(postbag.os, "environ", environment)
    monkeypatch.setitem(joined.KNOCK, "codex", postbag.knock_codex)
    joined.send("codex", "from claude to codex")
    child = json.loads(dump.read_text())
    hidden = {"CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN", "CODEX_SESSION_ID",
              "CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "POSTBAG_LEDGER"}
    assert hidden == postbag.HIDDEN_FROM_CHILD
    assert not hidden & child.keys()
    assert not {"tok", "/tmp/x.sock", "t-1"} & set(child.values())  # the fake door values under any name
    assert child["POSTBAG_CODEX"] == str(exe) and "PATH" in child and "HOME" in child
    assert child["CODEX_HOME"] == str(tmp_path / "runtime-home")
    assert joined.records()[-1]["body"] == "from claude to codex"


# fixture hazards --------------------------------------------------------------

def test_cli_fixture_bags_sees_only_the_tests_own_home(cli, tmp_path):
    home = cli.environment()["HOME"]
    assert home == str(tmp_path / "home") and os.path.isdir(home)
    empty = cli("bags")
    assert empty.returncode == 0, empty.stderr
    assert empty.stdout.startswith("0 bags found")
    assert cli("--bag", "review", "open", "--limit", "2").returncode == 0
    listed = cli("bags")
    assert listed.returncode == 0, listed.stderr
    assert listed.stdout.startswith("1 bag found") and "review" in listed.stdout
    assert (tmp_path / "home" / ".postbag" / "bags" / "review.jsonl").exists()


def test_cli_fixture_can_never_launch_the_desktop_codex(cli):
    sender, recipient, extra = prepare_exchange(cli, 1)
    result = cli("send", recipient, "no fake door", peer=sender)
    assert result.returncode == 1
    assert "no codex at" in result.stderr and "set POSTBAG_CODEX" in result.stderr
    assert "Traceback" not in result.stderr
    assert not any(json.loads(line)["kind"] == "letter" for line in cli.ledger.read_text().splitlines())


def test_be_and_session_fixtures_drop_the_running_conversation_id(bag, be, session, monkeypatch):
    conversation = "11111111-2222-3333-4444-555555555555"
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", conversation)
    be("claude")
    bag.join("claude")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", conversation)
    session("claude", "two")
    bag.join("claude", "ada")
    assert "CLAUDE_CODE_SESSION_ID" not in os.environ
    assert all("session_id" not in rec for rec in bag.records())
