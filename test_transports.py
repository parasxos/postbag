"""Failure contracts that should not require waiting for a real 30-second timeout."""
import errno
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
from contextlib import contextmanager

import pytest

import postbag
from test_postbag import bag, be, joined


def test_codex_timeout_is_an_actionable_transport_error(monkeypatch):
    monkeypatch.setenv("POSTBAG_CODEX", sys.executable)

    def timeout(argv, **kwargs):
        assert kwargs["timeout"] == 30
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(postbag.subprocess, "run", timeout)
    with pytest.raises(postbag.TransportError, match="did not return in 30 s") as error:
        postbag.knock_codex({"thread": "fake-thread"}, "hello")
    assert error.value.error_code == "submission_unknown"
    assert error.value.submission_state == "unknown"


def test_codex_nul_byte_is_an_actionable_transport_error(monkeypatch):
    monkeypatch.setenv("POSTBAG_CODEX", sys.executable)
    with pytest.raises(postbag.TransportError, match="could not start.*embedded null byte") as error:
        postbag.knock_codex({"thread": "fake-thread"}, "hello\0world")
    assert error.value.error_code == "invalid_input"
    assert error.value.submission_state == "not_submitted"


def test_codex_argument_size_failure_does_not_suggest_rejoining(joined, monkeypatch):
    monkeypatch.setenv("POSTBAG_CODEX", sys.executable)
    monkeypatch.setitem(joined.KNOCK, "codex", postbag.knock_codex)

    def too_large(argv, **kwargs):
        raise OSError(errno.E2BIG, "Argument list too long")

    monkeypatch.setattr(postbag.subprocess, "run", too_large)
    before = joined.ledger_path().read_bytes()
    with pytest.raises(postbag.Refusal, match="too large.*shorten") as error:
        joined.send("codex", "a valid body whose envelope exceeds the process limit")
    assert error.value.error_code == "invalid_input"
    assert error.value.submission_state == "not_submitted"
    assert "join codex" not in str(error.value)
    assert joined.ledger_path().read_bytes() == before


def test_codex_timeout_after_submission_warns_without_retry_or_append(joined, monkeypatch):
    monkeypatch.setenv("POSTBAG_CODEX", sys.executable)
    monkeypatch.setitem(joined.KNOCK, "codex", postbag.knock_codex)
    submissions = []

    def submitted_then_timed_out(argv, **kwargs):
        submissions.append(argv[-1])
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(postbag.subprocess, "run", submitted_then_timed_out)
    before = joined.ledger_path().read_bytes()
    with pytest.raises(postbag.Refusal, match="may already have reached.*do not resend") as error:
        joined.send("codex", "one attempted submission")
    assert error.value.error_code == "submission_unknown"
    assert error.value.submission_state == "unknown"
    assert len(submissions) == 1 and "one attempted submission" in submissions[0]
    assert joined.ledger_path().read_bytes() == before
    assert joined.budget() == 3


def test_codex_nonzero_exit_after_submission_has_an_unknown_outcome(joined, monkeypatch):
    monkeypatch.setenv("POSTBAG_CODEX", sys.executable)
    monkeypatch.setitem(joined.KNOCK, "codex", postbag.knock_codex)
    submissions = []

    def submitted_then_failed(argv, **kwargs):
        submissions.append(argv[-1])
        return subprocess.CompletedProcess(argv, 23)

    monkeypatch.setattr(postbag.subprocess, "run", submitted_then_failed)
    before = joined.ledger_path().read_bytes()
    with pytest.raises(postbag.Refusal, match="may already have reached.*do not resend") as error:
        joined.send("codex", "submission before process failure")
    assert error.value.error_code == "submission_unknown"
    assert error.value.submission_state == "unknown"
    assert "codex queue exited 23" in str(error.value)
    assert "join codex" not in str(error.value)
    assert len(submissions) == 1
    assert joined.ledger_path().read_bytes() == before
    assert joined.budget() == 3


@pytest.mark.parametrize("failure_at", ["connect", "write"])
def test_claude_connection_and_partial_write_failures_have_distinct_outcomes(
    joined, be, monkeypatch, failure_at,
):
    be("codex")
    monkeypatch.setitem(joined.KNOCK, "claude", postbag.knock_claude)
    writes = []

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, timeout):
            assert timeout == 30

        def connect(self, path):
            if failure_at == "connect":
                raise ConnectionRefusedError("closed test socket")

        def sendall(self, payload):
            writes.append(payload[:32])
            raise BrokenPipeError("partial test write")

    monkeypatch.setattr(postbag.socket, "socket", lambda *args: Socket())
    before = joined.ledger_path().read_bytes()
    with pytest.raises(postbag.Refusal) as error:
        joined.send("claude", "one attempted socket submission")
    if failure_at == "write":
        assert error.value.error_code == "submission_unknown"
        assert error.value.submission_state == "unknown"
        assert "may already have reached" in str(error.value)
        assert "do not resend" in str(error.value)
        assert len(writes) == 1
    else:
        assert error.value.error_code == "transport_unavailable"
        assert error.value.submission_state == "not_submitted"
        assert "door did not answer" in str(error.value)
        assert not writes
    assert joined.ledger_path().read_bytes() == before
    assert joined.budget() == 3


@pytest.mark.parametrize("wait", [True, False])
def test_send_returns_submission_metadata_without_body_or_credentials(joined, wait):
    result = joined.send("codex", "one recorded submission", wait=wait)
    assert result == {
        "bag": str(joined.ledger_path()), "from": "claude", "to": "codex", "record": 4,
        "exchange": 1, "letter": 1, "remaining": 2, "submission_state": "submitted",
    }


def test_missing_codex_binary_refuses_before_queueing(monkeypatch):
    monkeypatch.setenv("POSTBAG_CODEX", "/nonexistent-postbag-test/codex")
    with pytest.raises(SystemExit, match="set POSTBAG_CODEX.*stop and ask the human"):
        postbag.knock_codex({"thread": "fake-thread"}, "hello")


def test_failed_append_reports_that_submission_already_happened(joined, monkeypatch):
    original = joined.ledger

    @contextmanager
    def broken_append(**kwargs):
        with original(**kwargs):
            def write(rec):
                raise OSError("simulated disk full")
            yield write

    monkeypatch.setattr(joined, "ledger", broken_append)
    with pytest.raises(SystemExit) as error:
        joined.send("codex", "one submission")
    message = str(error.value)
    assert any(word in message for word in ("submitted", "submission", "may already", "reached"))
    assert "recording could not be confirmed" in message
    assert "do not resend" in message and "inspecting the bag" in message
    assert "stop and ask the human" in message
    assert error.value.error_code == "recording_failed"
    assert error.value.submission_state == "submitted"
    assert len(joined.KNOCKED) == 1
    assert not any(rec["kind"] == "letter" for rec in joined.records())


def test_buffered_append_failure_preserves_submission_warning_after_close(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("CLAUDE_", "CODEX_", "POSTBAG_"))
    }
    environment["POSTBAG_LEDGER"] = str(ledger)
    runner = textwrap.dedent("""
        import os
        import resource
        import runpy
        import signal
        import sys

        bag = runpy.run_path(sys.argv[1])
        bag['open_exchange'](1)
        os.environ['CODEX_SESSION_ID'] = 'fake-thread-not-a-live-session'
        bag['join']('codex')
        del os.environ['CODEX_SESSION_ID']
        os.environ['CLAUDE_CODE_MESSAGING_SOCKET'] = '/tmp/unused-postbag-test.sock'
        os.environ['CLAUDE_CODE_MESSAGING_TOKEN'] = 'fake-token-not-a-credential'
        bag['join']('claude')
        bag['KNOCK']['codex'] = lambda door, text: print('FAKE_DOOR_SUBMITTED', flush=True)

        # Only this child gets the limit. The send buffers data, then both flush
        # and close encounter EFBIG, reproducing the real double-failure path.
        size = os.stat(os.environ['POSTBAG_LEDGER']).st_size
        signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
        resource.setrlimit(resource.RLIMIT_FSIZE, (size, size))
        bag['main'](['send', 'codex', 'one submission'])
    """)

    result = subprocess.run(
        [sys.executable, "-c", runner, str(Path(postbag.__file__).resolve())],
        env=environment, capture_output=True, text=True, timeout=5,
    )

    assert result.returncode != 0
    assert result.stdout.count("FAKE_DOOR_SUBMITTED") == 1
    assert any(word in result.stderr for word in ("submitted", "submission", "may already", "reached"))
    assert "recording could not be confirmed" in result.stderr
    assert "do not resend" in result.stderr and "inspecting the bag" in result.stderr
    assert "stop and ask the human" in result.stderr
    assert "Traceback" not in result.stderr
    records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert not any(record["kind"] == "letter" for record in records)


def test_latest_join_replaces_the_recipient_door(joined, be, monkeypatch):
    be("codex")
    monkeypatch.setenv("CODEX_SESSION_ID", "replacement-thread")
    joined.join("codex")
    be("claude")
    joined.send("codex", "new session")
    assert joined.KNOCKED[-1][1]["thread"] == "replacement-thread"
