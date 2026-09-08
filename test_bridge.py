"""Unit tests: ledger, doors, budget. Doors are faked; delivery is tested live."""
import importlib.util
import json
import os
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_loader("bridge", loader=None)


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIDGE_HOME", str(tmp_path))
    monkeypatch.setenv("BRIDGE_LIMIT", "3")
    src = Path(__file__).with_name("bridge").read_text()
    mod = importlib.util.module_from_spec(SPEC)
    exec(compile(src, "bridge", "exec"), mod.__dict__)
    mod.KNOCKED = []
    mod.KNOCK = {peer: (lambda d, t, peer=peer: mod.KNOCKED.append((peer, d, t))) for peer in mod.PEERS}
    return mod


def joined(bridge, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_SOCKET", "/tmp/x.sock")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_TOKEN", "tok")
    bridge.join("claude")
    bridge.join("codex", thread="t-1")


def test_join_publishes_doors(bridge, monkeypatch):
    joined(bridge, monkeypatch)
    assert bridge.door("claude") == {"socket": "/tmp/x.sock", "token": "tok"}
    assert bridge.door("codex") == {"thread": "t-1"}
    assert [r["kind"] for r in bridge.records()] == ["join", "join"]


def test_join_needs_a_session(bridge, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_MESSAGING_SOCKET", raising=False)
    monkeypatch.delenv("CODEX_SESSION_ID", raising=False)
    with pytest.raises(SystemExit):
        bridge.join("claude")
    with pytest.raises(SystemExit):
        bridge.join("codex")


def test_sender_is_the_other_peer(bridge, monkeypatch):
    joined(bridge, monkeypatch)
    bridge.open_exchange("t")
    bridge.send("codex", "hello")
    rec = bridge.records()[-1]
    assert (rec["from"], rec["to"], rec["body"]) == ("claude", "codex", "hello")
    peer, door, text = bridge.KNOCKED[0]
    assert peer == "codex" and door == {"thread": "t-1"}
    assert text.startswith(f"Letter {rec['n']} from claude") and 'bridge send claude' in text and text.endswith("hello")


def test_letter_recorded_only_after_delivery(bridge, monkeypatch):
    joined(bridge, monkeypatch)
    bridge.open_exchange("t")

    def broken(door, text):
        raise OSError("door closed")

    bridge.KNOCK["claude"] = broken
    with pytest.raises(OSError):
        bridge.send("claude", "x")
    assert all(r["kind"] != "letter" for r in bridge.records())


def test_budget_refuses_then_open_renews(bridge, monkeypatch):
    joined(bridge, monkeypatch)
    bridge.open_exchange("t")
    for i in range(3):
        bridge.send("codex", str(i))
    with pytest.raises(SystemExit, match="budget"):
        bridge.send("claude", "one too many")
    bridge.open_exchange("again")
    bridge.send("claude", "fine")
    assert len(bridge.exchange()) == 1


def test_unjoined_recipient(bridge, monkeypatch):
    bridge.open_exchange("t")
    with pytest.raises(SystemExit, match="has not joined"):
        bridge.send("codex", "x")


def test_read_prints_ledger(bridge, monkeypatch, capsys):
    joined(bridge, monkeypatch)
    bridge.open_exchange("topic")
    bridge.send("codex", "line one\nline two")
    capsys.readouterr()
    bridge.read(10)
    out = capsys.readouterr().out
    assert "topic (3 letters)" in out and "claude -> codex" in out and "      line two" in out
