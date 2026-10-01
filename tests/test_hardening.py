"""Regression tests using private ledgers and fake vendor doors only."""

import fcntl
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import textwrap
from concurrent.futures import ThreadPoolExecutor

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ("postbag.py" if (ROOT / "postbag.py").exists() else "postbag")
SESSION_VARS = {
    "claude": {
        "CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/postbag-test-unused.sock",
        "CLAUDE_CODE_MESSAGING_TOKEN": "test-token-not-a-credential",
    },
    "codex": {"CODEX_SESSION_ID": "test-thread-not-a-live-session"},
}


@pytest.fixture
def cli(tmp_path):
    """Every invocation gets a private ledger and no inherited vendor identity."""
    base = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("CLAUDE_", "CODEX_", "POSTBAG_"))
    }
    ledger = tmp_path / "state" / "ledger.jsonl"
    base["POSTBAG_LEDGER"] = str(ledger)
    # A codex-bound send that forgets fake_codex must refuse, never launch the desktop binary.
    base["POSTBAG_CODEX"] = str(tmp_path / "no-such-codex")
    # bags always scans HOME/.postbag, so HOME must never be the developer's own.
    home = tmp_path / "home"
    home.mkdir()
    base["HOME"] = str(home)

    def environment(peer=None, extra=None):
        return {**base, **SESSION_VARS.get(peer, {}), **(extra or {})}

    def run(*args, peer=None, extra=None, **kwargs):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            env=environment(peer, extra), capture_output=True, text=True,
            timeout=10, **kwargs,
        )

    run.ledger = ledger
    run.environment = environment
    return run


@pytest.fixture
def fake_codex(tmp_path):
    executable = tmp_path / "fake-codex"
    capture = tmp_path / "queued.jsonl"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys, time\n"
        "time.sleep(0.02)\n"
        "with open(os.environ['POSTBAG_TEST_CAPTURE'], 'a') as capture:\n"
        "    capture.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if os.environ.get('POSTBAG_TEST_REJECT'):\n"
        "    print('fake queue rejected the message for thread', sys.argv[2], file=sys.stderr)\n"
        "    sys.exit(23)\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    return {
        "POSTBAG_CODEX": str(executable),
        "POSTBAG_TEST_CAPTURE": str(capture),
    }


def assert_ok(result):
    assert result.returncode == 0, result.stderr


def prepare_pair(cli, *, same_vendor=False):
    """Two joined peers. Returns the sender's vendor, the recipient's address and the sender's extra env."""
    if same_vendor:
        sender, recipient = "codex", "@bob"
        sender_extra = {"CODEX_SESSION_ID": "sender-thread-not-a-live-session"}
        assert_ok(cli("join", "codex", "ada", peer=sender, extra=sender_extra))
        assert_ok(cli("join", "codex", "bob", peer="codex"))
    else:
        sender, recipient, sender_extra = "claude", "codex", {}
        assert_ok(cli("join", "claude", peer="claude"))
        assert_ok(cli("join", "codex", peer="codex"))
    return sender, recipient, sender_extra


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def read_history(cli, letter_count):
    records = [{"n": i + 1, "at": "2026-09-09T08:00:01+02:00", "kind": "letter",
                "from": "claude", "to": "codex", "body": "x" * 1024}
               for i in range(letter_count)]
    original = "".join(json.dumps(record) + "\n" for record in records).encode()
    cli.ledger.parent.mkdir()
    cli.ledger.write_bytes(original)
    return original


@pytest.mark.parametrize("letter_count", [0, 400], ids=["buffered", "streaming"])
def test_read_exits_quietly_when_its_output_pipe_is_closed(cli, letter_count):
    original = read_history(cli, letter_count)
    reader, writer = os.pipe()
    os.close(reader)
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "read"], env=cli.environment(),
            stdout=writer, stderr=subprocess.PIPE, text=True, timeout=10,
        )
    finally:
        os.close(writer)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert cli.ledger.read_bytes() == original


def test_read_can_be_piped_to_head(cli):
    original = read_history(cli, 400)
    with subprocess.Popen(
        [sys.executable, str(SCRIPT), "read"], env=cli.environment(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ) as producer:
        consumer = subprocess.run(
            ["head", "-n", "1"], stdin=producer.stdout,
            capture_output=True, text=True, timeout=10,
        )
        producer.stdout.close()
        producer.stdout = None
        _, stderr = producer.communicate(timeout=10)

    assert consumer.returncode == producer.returncode == 0, stderr
    assert consumer.stdout == f"in bag {cli.ledger}: none. 400 letters.\n"
    assert consumer.stderr == stderr == ""
    assert cli.ledger.read_bytes() == original


@pytest.mark.parametrize("record", [
    pytest.param(None, id="null"),
    pytest.param([], id="list"),
    pytest.param({}, id="empty-object"),
    pytest.param(
        {"n": 1, "at": "2026-09-08T00:00:00", "kind": "unknown"}, id="unknown-kind",
    ),
    pytest.param(
        {"n": 1, "at": "2026-09-08T00:00:00", "kind": "open", "limit": "3"},
        id="string-limit",
    ),
    pytest.param(
        {"n": 1, "at": "2026-09-08T00:00:00", "kind": "open", "limit": True},
        id="bool-limit",
    ),
    pytest.param(
        {"n": 1, "at": "2026-09-08T00:00:00", "kind": "join", "peer": "claude"},
        id="missing-door",
    ),
    pytest.param(
        {"n": 1, "at": "2026-09-08T00:00:00", "kind": "join", "peer": []},
        id="list-peer",
    ),
    pytest.param(
        {"n": 1, "at": "2026-09-08T00:00:00", "kind": "letter", "from": [],
         "to": "codex", "body": "hello"}, id="list-sender",
    ),
    pytest.param(
        {"n": True, "at": "2026-09-08T00:00:00", "kind": "open", "limit": 1},
        id="bool-number",
    ),
    pytest.param(
        {"n": 1.0, "at": "2026-09-08T00:00:00", "kind": "open", "limit": 1},
        id="float-number",
    ),
    pytest.param(
        {"n": 1, "at": "", "kind": "open", "limit": 1}, id="empty-timestamp",
    ),
    pytest.param(
        {"n": 1, "at": "2026-09-08T00:00:00", "kind": "letter", "from": "claude",
         "to": "codex", "body": ""}, id="empty-body",
    ),
])
def test_valid_json_with_invalid_record_shape_is_a_clean_refusal(cli, record):
    cli.ledger.parent.mkdir()
    original = json.dumps(record) + "\n"
    cli.ledger.write_text(original, encoding="utf-8")

    result = cli("read")

    assert result.returncode != 0
    assert "postbag:" in result.stderr
    assert "stop and ask the human" in result.stderr
    assert "Traceback" not in result.stderr
    assert cli.ledger.read_text(encoding="utf-8") == original


def test_invalid_utf8_ledger_is_a_clean_refusal(cli):
    cli.ledger.parent.mkdir()
    original = b'{"n": 1, "at": "\xff"}\n'
    cli.ledger.write_bytes(original)

    result = cli("read")

    assert result.returncode != 0
    assert "postbag:" in result.stderr
    assert "stop and ask the human" in result.stderr
    assert "Traceback" not in result.stderr
    assert cli.ledger.read_bytes() == original


@pytest.mark.parametrize("separator", ["\0", "\x1b", "\x7f"])
def test_legacy_control_timestamp_reads_canonically_without_changing_history(cli, separator):
    cli.ledger.parent.mkdir()
    original = json.dumps({"n": 1, "at": f"2026-09-08{separator}10:00:00+02:00",
                           "kind": "open", "limit": 1}) + "\n"
    cli.ledger.write_text(original, encoding="utf-8")
    result = cli("read")
    assert_ok(result)
    assert "2026-09-08T10:00:00+02:00" in result.stdout
    assert separator not in result.stdout + result.stderr
    assert cli.ledger.read_text(encoding="utf-8") == original


def test_legacy_control_timestamp_in_takeover_is_canonical(cli):
    assert_ok(cli("join", "codex", peer="codex"))
    record = rows(cli.ledger)[0]
    record["at"] = "2026-09-08\x1b10:00:00+02:00"
    cli.ledger.write_text(json.dumps(record) + "\n", encoding="utf-8")
    result = cli("join", "codex", peer="codex", extra={"CODEX_SESSION_ID": "fake-replacement"})
    assert_ok(result)
    assert "taken from the codex door that joined at 2026-09-08T10:00:00+02:00" in result.stdout
    assert "\x1b" not in result.stdout + result.stderr
    assert rows(cli.ledger)[0] == record


@pytest.mark.parametrize("preexisting", [False, True])
def test_join_keeps_ledger_private_even_with_permissive_umask(cli, preexisting):
    if preexisting:
        cli.ledger.parent.mkdir()
        cli.ledger.touch()
        cli.ledger.chmod(0o600)

    assert_ok(cli("join", "codex", peer="codex", umask=0))

    assert stat.S_IMODE(cli.ledger.stat().st_mode) == 0o600
    if not preexisting:
        assert stat.S_IMODE(cli.ledger.parent.stat().st_mode) == 0o700


def test_join_refuses_an_exposed_ledger_without_changing_it(cli):
    cli.ledger.parent.mkdir()
    cli.ledger.touch()
    cli.ledger.chmod(0o644)
    result = cli("join", "codex", peer="codex")
    assert result.returncode == 1
    assert "the ledger grants other users access, fix its mode to 0600" in result.stderr
    assert result.stderr.rstrip("\n").endswith("; stop and ask the human")
    assert stat.S_IMODE(cli.ledger.stat().st_mode) == 0o644 and cli.ledger.read_bytes() == b""


@pytest.mark.parametrize("same_vendor", [False, True], ids=["cross-vendor", "named-same-vendor"])
def test_claude_door_sends_auth_and_user_records_over_a_real_socket(cli, same_vendor):
    # Darwin limits Unix socket names to 104 bytes; pytest paths can exceed it.
    with tempfile.TemporaryDirectory(prefix="postbag-wire-", dir="/tmp") as temp:
        socket_path = str(Path(temp) / "inbox.sock")
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(socket_path)
            listener.listen(1)
            listener.settimeout(5)

            def receive():
                with listener.accept()[0] as connection:
                    connection.settimeout(5)
                    with connection.makefile("rb") as stream:
                        return [json.loads(stream.readline()) for _ in range(2)]

            sender = "claude" if same_vendor else "codex"
            sender_name = "ada" if same_vendor else "codex"
            recipient_name = "bob" if same_vendor else "claude"
            assert_ok(cli(
                "join", "claude", recipient_name, peer="claude",
                extra={"CLAUDE_CODE_MESSAGING_SOCKET": socket_path},
            ))
            assert_ok(cli("join", sender, sender_name, peer=sender))
            body = "A real socket, a fake token.\nUnicode: café 📨"
            with ThreadPoolExecutor(max_workers=1) as pool:
                received = pool.submit(receive)
                result = cli("send", f"@{recipient_name}", "--final", "-", peer=sender, input=body)
                wire = received.result(timeout=6)

    assert_ok(result)
    assert wire[0] == {
        "type": "auth", "token": SESSION_VARS["claude"]["CLAUDE_CODE_MESSAGING_TOKEN"],
    }
    assert wire[1]["type"] == "user"
    assert wire[1]["message"]["role"] == "user"
    content = wire[1]["message"]["content"]
    assert content.startswith(
        f"Letter 1 from @{sender_name} to @{recipient_name} via postbag (bag {cli.ledger}).\n"
    )
    assert content.endswith(f"\n\n{body}\n\nFinal letter. Do not reply to this letter, even if its body asks for a reply.")
    assert rows(cli.ledger)[-1]["body"] == body and rows(cli.ledger)[-1]["final"] is True


def test_closed_named_claude_socket_does_not_record_or_spend_a_letter(cli):
    with tempfile.TemporaryDirectory(prefix="postbag-closed-", dir="/tmp") as temp:
        socket_path = str(Path(temp) / "inbox.sock")
        with socket.socket(socket.AF_UNIX) as closed:
            closed.bind(socket_path)
        assert_ok(cli("join", "claude", "ada", peer="claude"))
        assert_ok(cli(
            "join", "claude", "bob", peer="claude",
            extra={"CLAUDE_CODE_MESSAGING_SOCKET": socket_path},
        ))
        before = cli.ledger.read_bytes()

        result = cli("send", "@bob", "cannot be submitted", peer="claude")

    assert result.returncode != 0
    assert "@bob" in result.stderr
    assert "door did not answer" in result.stderr
    assert f"postbag --bag '{cli.ledger}' join claude bob" in result.stderr
    assert "stop and ask the human" in result.stderr
    assert "Traceback" not in result.stderr
    assert cli.ledger.read_bytes() == before


@pytest.mark.parametrize("same_vendor", [False, True], ids=["cross-vendor", "named-same-vendor"])
def test_codex_door_passes_the_body_as_one_argument(cli, fake_codex, same_vendor):
    sender, recipient, sender_extra = prepare_pair(cli, same_vendor=same_vendor)
    body = "quotes: ' and \"; $(never-run)\nsecond line"

    assert_ok(cli("send", recipient, body, peer=sender, extra={**fake_codex, **sender_extra}))

    calls = rows(Path(fake_codex["POSTBAG_TEST_CAPTURE"]))
    assert len(calls) == 1
    assert calls[0][:4] == [
        "queue", "--thread", SESSION_VARS["codex"]["CODEX_SESSION_ID"], "--message",
    ]
    assert len(calls[0]) == 5
    content = calls[0][4]
    sender_name, recipient_name = ("ada", "bob") if same_vendor else ("claude", "codex")
    assert content.startswith(
        f"Letter 1 from @{sender_name} to @{recipient_name} via postbag (bag {cli.ledger}).\n"
    )
    assert f"\n\n{body}\n\nReply only when a reply advances the task." in content
    assert "needs no answer.\nIf it needs an answer, reply with:\n" in content
    assert f"postbag --bag '{cli.ledger}' send @{sender_name} - <<'POSTBAG'" in content
    assert rows(cli.ledger)[-1]["body"] == body


@pytest.mark.parametrize("sender, recipient", [("claude", "codex"), ("codex", "claude")])
def test_nul_stdin_refuses_before_contacting_either_vendor(cli, fake_codex, sender, recipient):
    prepare_pair(cli)
    before = cli.ledger.read_bytes()
    result = cli("send", recipient, "-", peer=sender, extra=fake_codex, input="hello\0world")
    assert result.returncode == 1
    assert "NUL byte" in result.stderr
    assert "stop and ask the human" in result.stderr
    assert "Traceback" not in result.stderr
    assert cli.ledger.read_bytes() == before
    assert not Path(fake_codex["POSTBAG_TEST_CAPTURE"]).exists()


def test_oversized_codex_stdin_is_a_clean_input_refusal(cli, fake_codex):
    sender, recipient, extra = prepare_pair(cli)
    before = cli.ledger.read_bytes()
    # This exceeds macOS ARG_MAX and Linux's per-argument limit.
    result = cli("send", recipient, "-", peer=sender, extra={**fake_codex, **extra}, input="x" * (1 << 20))
    assert result.returncode == 1
    assert "too large for codex queue, shorten it" in result.stderr
    assert "stop and ask the human" in result.stderr
    assert "Traceback" not in result.stderr
    assert "join codex" not in result.stderr
    assert cli.ledger.read_bytes() == before
    assert not Path(fake_codex["POSTBAG_TEST_CAPTURE"]).exists()


@pytest.mark.parametrize("same_vendor", [False, True], ids=["cross-vendor", "named-same-vendor"])
def test_rejected_codex_queue_does_not_record_a_letter(cli, fake_codex, same_vendor):
    sender, recipient, sender_extra = prepare_pair(cli, same_vendor=same_vendor)
    before = cli.ledger.read_bytes()

    result = cli(
        "send", recipient, "rejected", peer=sender,
        extra={**fake_codex, **sender_extra, "POSTBAG_TEST_REJECT": "1"},
    )

    assert result.returncode != 0
    assert "codex queue exited 23" in result.stderr
    assert "may already have reached" in result.stderr
    assert "do not resend" in result.stderr
    # A stale door's stderr names its thread, a door field: the refusal relays none of it.
    assert "fake queue rejected" not in result.stderr
    assert SESSION_VARS["codex"]["CODEX_SESSION_ID"] not in result.stderr
    assert "stop and ask the human" in result.stderr
    assert "Traceback" not in result.stderr
    assert cli.ledger.read_bytes() == before
    assert_ok(cli("send", recipient, "accepted", peer=sender, extra={**fake_codex, **sender_extra}))
    assert len([r for r in rows(cli.ledger) if r["kind"] == "letter"]) == 1


@pytest.mark.parametrize("operation", ["ledger", "join", "send"])
def test_nonblocking_mutations_refuse_a_busy_ledger_before_delivery(cli, operation):
    prepare_pair(cli)
    before = cli.ledger.read_bytes()
    runner = textwrap.dedent("""
        import json, runpy, sys
        bag = runpy.run_path(sys.argv[1])
        def no_contact(*args):
            raise AssertionError('a busy-ledger request contacted a door')
        for vendor in bag['KNOCK']:
            bag['KNOCK'][vendor] = no_contact
        try:
            if sys.argv[2] == 'ledger':
                with bag['ledger'](wait=False):
                    raise AssertionError('busy ledger was acquired')
            elif sys.argv[2] == 'join':
                bag['join']('claude', wait=False)
            else:
                bag['send']('codex', 'must not be sent later', wait=False)
        except bag['Refusal'] as error:
            print(json.dumps({'error_code': error.error_code,
                              'submission_state': error.submission_state,
                              'message': str(error)}))
        else:
            raise AssertionError('busy operation did not refuse')
    """)
    with cli.ledger.open("r+") as holder:
        fcntl.flock(holder, fcntl.LOCK_EX)
        result = subprocess.run(
            [sys.executable, "-c", runner, str(SCRIPT), operation], env=cli.environment("claude"),
            capture_output=True, text=True, timeout=3,
        )
    assert_ok(result)
    refusal = json.loads(result.stdout)
    assert refusal["error_code"] == "ledger_busy"
    assert refusal["submission_state"] == "not_submitted"
    assert "stop and ask the human" in refusal["message"]
    assert result.stderr == ""
    assert cli.ledger.read_bytes() == before


def test_inventory_returns_data_without_output_or_credential_fields(tmp_path, monkeypatch, capsys):
    import postbag

    monkeypatch.setenv("HOME", str(tmp_path))
    ledger = tmp_path / ".postbag" / "ledger.jsonl"
    monkeypatch.setenv("POSTBAG_LEDGER", str(ledger))
    ledger.parent.mkdir()
    conversation = "11111111-2222-3333-4444-555555555555"
    records = [
        {"n": 1, "at": "2026-09-30T10:00:00+02:00", "kind": "open", "limit": 2},
        {"n": 2, "at": "2026-09-30T10:00:00+02:00", "kind": "join", "peer": "ada",
         "vendor": "claude", "socket": "/tmp/fake-socket", "token": "fake-secret-token",
         "session_id": conversation},
    ]
    original = "".join(json.dumps(record) + "\n" for record in records)
    ledger.write_text(original, encoding="utf-8")
    assert postbag.inventory() == (
        [("default", 0, "-", [("ada", "claude")])],
        {"letters": 0, "empty": 1, "unavailable": 0},
        {"default": [("ada", conversation)]}, [],
    )
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    assert ledger.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("same_vendor", [False, True], ids=["cross-vendor", "named-same-vendor"])
def test_concurrent_cli_sends_get_consecutive_numbers_in_ledger_order(cli, fake_codex, same_vendor):
    count = 8
    sender, recipient, sender_extra = prepare_pair(cli, same_vendor=same_vendor)
    processes = []
    try:
        for number in range(count):
            # Named Codex peers send in both directions into the same bag.
            reverse = same_vendor and number % 2
            target = "@ada" if reverse else recipient
            extra = {} if reverse else sender_extra
            processes.append(subprocess.Popen(
                [sys.executable, str(SCRIPT), "send", target, f"body-{number}"],
                env=cli.environment(sender, {**fake_codex, **extra}),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            ))
        results = [process.communicate(timeout=10) for process in processes]
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

    assert [process.returncode for process in processes] == [0] * count, [r[1] for r in results]
    ledger = rows(cli.ledger)
    assert [r["n"] for r in ledger] == list(range(1, len(ledger) + 1))
    letters = [r for r in ledger if r["kind"] == "letter"]
    assert len(letters) == count
    assert len({r["body"] for r in letters}) == count
    calls = rows(Path(fake_codex["POSTBAG_TEST_CAPTURE"]))
    assert len(calls) == count
    assert all("Final letter" not in call[-1] for call in calls)
    for number, (letter, call) in enumerate(zip(letters, calls), 1):
        assert call[-1].startswith(
            f"Letter {number} from @{letter['from']} to @{letter['to']} "
            f"via postbag (bag {cli.ledger}).\n"
        )
        if same_vendor:
            expected_thread = (sender_extra["CODEX_SESSION_ID"] if letter["to"] == "ada"
                               else SESSION_VARS["codex"]["CODEX_SESSION_ID"])
            assert call[2] == expected_thread


@pytest.mark.parametrize("args, said", [
    (["join", "gemini"], "invalid choice"),
    (["send", "@bob"], "the following arguments are required: body"),
    (["open", "--limit", "3"], "invalid choice: 'open'"),
    (["read", "0"], "must be at least 1"),
    (["deliver"], "invalid choice"),
    ([], "the following arguments are required: verb"),
])
def test_a_usage_mistake_is_a_refusal_that_says_stop(cli, args, said):
    result = cli(*args, peer="claude")
    assert result.returncode == 1
    assert result.stderr.startswith("postbag: ") and said in result.stderr
    assert result.stderr.rstrip("\n").endswith("; stop and ask the human")
    assert "Traceback" not in result.stderr
    assert not cli.ledger.exists()


@pytest.mark.parametrize("args", [["--help"], ["--version"], ["send", "--help"]])
def test_help_and_version_are_not_refusals(cli, args):
    result = cli(*args)
    assert result.returncode == 0, result.stderr
    assert "stop and ask the human" not in result.stdout + result.stderr
    assert "postbag" in result.stdout


def test_send_and_read_help_describe_their_arguments(cli):
    send = cli("send", "--help")
    assert send.returncode == 0 and "--final" in send.stdout and "asks for no reply" in send.stdout
    read = cli("read", "--help")
    assert read.returncode == 0 and "last N records" in read.stdout
    assert not cli.ledger.exists()


def test_join_with_an_explicit_empty_name_refuses_instead_of_defaulting(cli):
    result = cli("join", "codex", "", peer="codex")
    assert result.returncode == 1
    assert "a name must match" in result.stderr and "stop and ask the human" in result.stderr
    assert not cli.ledger.exists()
    assert_ok(cli("join", "codex", peer="codex"))
    assert rows(cli.ledger)[-1]["peer"] == "codex"


def test_read_waits_for_an_exclusive_writer_to_finish_a_record(cli):
    cli.ledger.parent.mkdir()
    record = json.dumps({
        "n": 1, "at": "2026-09-08T00:00:00", "kind": "letter", "from": "ada", "to": "bob", "body": "x",
    }) + "\n"
    # Signal readiness after loading Python/module imports, before invoking read.
    runner = (
        "import runpy, sys; "
        "ns = runpy.run_path(sys.argv[1]); "
        "print('reader ready', flush=True); "
        "ns['main'](['read'])"
    )
    process = None
    with cli.ledger.open("w", encoding="utf-8") as writer:
        fcntl.flock(writer, fcntl.LOCK_EX)
        writer.write(record[:8])
        writer.flush()
        try:
            process = subprocess.Popen(
                [sys.executable, "-u", "-c", runner, str(SCRIPT)],
                env=cli.environment(), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
            # select keeps even the startup handshake bounded on POSIX.
            import select
            assert select.select([process.stdout], [], [], 5)[0], "reader did not start"
            assert process.stdout.readline() == "reader ready\n"
            with pytest.raises(subprocess.TimeoutExpired):
                process.wait(timeout=0.2)
            writer.write(record[8:])
            writer.flush()
            fcntl.flock(writer, fcntl.LOCK_UN)
            stdout, stderr = process.communicate(timeout=5)
            assert process.returncode == 0, stderr
            assert "1 letter." in stdout
        finally:
            fcntl.flock(writer, fcntl.LOCK_UN)
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
