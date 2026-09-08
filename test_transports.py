"""Failure contracts that should not require waiting for a real 30-second timeout."""
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
    with pytest.raises(OSError, match="did not return in 30 s"):
        postbag.knock_codex({"thread": "fake-thread"}, "hello")


def test_missing_codex_binary_refuses_before_queueing(monkeypatch):
    monkeypatch.setenv("POSTBAG_CODEX", "/nonexistent-postbag-test/codex")
    with pytest.raises(SystemExit, match="set POSTBAG_CODEX.*stop and ask the human"):
        postbag.knock_codex({"thread": "fake-thread"}, "hello")


def test_failed_append_reports_that_submission_already_happened(joined, monkeypatch):
    original = joined.ledger

    @contextmanager
    def broken_append():
        with original():
            def write(rec):
                raise OSError("simulated disk full")
            yield write

    monkeypatch.setattr(joined, "ledger", broken_append)
    with pytest.raises(SystemExit) as error:
        joined.send("codex", "one submission")
    message = str(error.value)
    assert any(word in message for word in ("submitted", "submission", "may already", "reached"))
    assert "not recorded" in message
    assert "do not resend" in message
    assert "stop and ask the human" in message
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
    assert "not recorded" in result.stderr
    assert "do not resend" in result.stderr
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
