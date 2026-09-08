"""Failure contracts that should not require waiting for a real 30-second timeout."""
import subprocess
import sys
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


def test_latest_join_replaces_the_recipient_door(joined, be, monkeypatch):
    be("codex")
    monkeypatch.setenv("CODEX_SESSION_ID", "replacement-thread")
    joined.join("codex")
    be("claude")
    joined.send("codex", "new session")
    assert joined.KNOCKED[-1][1]["thread"] == "replacement-thread"
