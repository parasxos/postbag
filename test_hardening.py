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
from concurrent.futures import ThreadPoolExecutor

import pytest


ROOT = Path(__file__).resolve().parent
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
        "    print('fake queue rejected the message', file=sys.stderr)\n"
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


def prepare_exchange(cli, limit):
    assert_ok(cli("join", "claude", peer="claude"))
    assert_ok(cli("join", "codex", peer="codex"))
    assert_ok(cli("open", "--limit", str(limit)))


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


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


@pytest.mark.parametrize("preexisting", [False, True])
def test_join_keeps_ledger_private_even_with_permissive_umask(cli, preexisting):
    if preexisting:
        cli.ledger.parent.mkdir()
        cli.ledger.touch()
        cli.ledger.chmod(0o644)

    assert_ok(cli("join", "codex", peer="codex", umask=0))

    assert stat.S_IMODE(cli.ledger.stat().st_mode) == 0o600
    if not preexisting:
        assert stat.S_IMODE(cli.ledger.parent.stat().st_mode) == 0o700


def test_claude_door_sends_auth_and_user_records_over_a_real_socket(cli):
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

            assert_ok(cli(
                "join", "claude", peer="claude",
                extra={"CLAUDE_CODE_MESSAGING_SOCKET": socket_path},
            ))
            assert_ok(cli("open", "--limit", "1"))
            body = "A real socket, a fake token.\nUnicode: café 📨"
            with ThreadPoolExecutor(max_workers=1) as pool:
                received = pool.submit(receive)
                result = cli("send", "claude", "-", peer="codex", input=body)
                wire = received.result(timeout=6)

    assert_ok(result)
    assert wire[0] == {
        "type": "auth", "token": SESSION_VARS["claude"]["CLAUDE_CODE_MESSAGING_TOKEN"],
    }
    assert wire[1]["type"] == "user"
    assert wire[1]["message"]["role"] == "user"
    content = wire[1]["message"]["content"]
    assert "do not reply" in content
    assert content.endswith(body)
    assert rows(cli.ledger)[-1]["body"] == body


def test_codex_door_passes_the_body_as_one_argument(cli, fake_codex):
    prepare_exchange(cli, 2)
    body = "quotes: ' and \"; $(never-run)\nsecond line"

    assert_ok(cli("send", "codex", body, peer="claude", extra=fake_codex))

    calls = rows(Path(fake_codex["POSTBAG_TEST_CAPTURE"]))
    assert len(calls) == 1
    assert calls[0][:4] == [
        "queue", "--thread", SESSION_VARS["codex"]["CODEX_SESSION_ID"], "--message",
    ]
    assert len(calls[0]) == 5
    assert calls[0][4].endswith(body)
    assert rows(cli.ledger)[-1]["body"] == body


def test_rejected_codex_queue_does_not_record_or_spend_a_letter(cli, fake_codex):
    prepare_exchange(cli, 1)
    before = cli.ledger.read_bytes()

    result = cli(
        "send", "codex", "rejected", peer="claude",
        extra={**fake_codex, "POSTBAG_TEST_REJECT": "1"},
    )

    assert result.returncode != 0
    assert "fake queue rejected" in result.stderr
    assert "stop and ask the human" in result.stderr
    assert "Traceback" not in result.stderr
    assert cli.ledger.read_bytes() == before
    assert_ok(cli("send", "codex", "accepted", peer="claude", extra=fake_codex))
    assert len([r for r in rows(cli.ledger) if r["kind"] == "letter"]) == 1


def test_concurrent_cli_sends_share_one_budget_and_consecutive_numbers(cli, fake_codex):
    limit = 4
    prepare_exchange(cli, limit)
    processes = []
    try:
        for number in range(8):
            processes.append(subprocess.Popen(
                [sys.executable, str(SCRIPT), "send", "codex", f"body-{number}"],
                env=cli.environment("claude", fake_codex),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            ))
        results = [process.communicate(timeout=10) for process in processes]
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

    assert sum(process.returncode == 0 for process in processes) == limit
    for process, (_, stderr) in zip(processes, results):
        if process.returncode:
            assert "spent" in stderr
            assert "Traceback" not in stderr
    ledger = rows(cli.ledger)
    assert [r["n"] for r in ledger] == list(range(1, len(ledger) + 1))
    letters = [r for r in ledger if r["kind"] == "letter"]
    assert len(letters) == limit
    assert len({r["body"] for r in letters}) == limit
    calls = rows(Path(fake_codex["POSTBAG_TEST_CAPTURE"]))
    assert len(calls) == limit
    assert "do not reply" in calls[-1][-1]


def test_read_waits_for_an_exclusive_writer_to_finish_a_record(cli):
    cli.ledger.parent.mkdir()
    record = json.dumps({
        "n": 1, "at": "2026-09-08T00:00:00", "kind": "open", "limit": 1,
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
            assert "1 letters" in stdout
        finally:
            fcntl.flock(writer, fcntl.LOCK_UN)
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
