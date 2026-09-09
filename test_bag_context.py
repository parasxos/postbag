"""Bag selection stays fixed during a command and never authorizes implicit creation."""
import json
import os
from pathlib import Path

import pytest

import postbag


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("POSTBAG_LEDGER", raising=False)
    for fields in postbag.SESSION.values():
        for variable in fields.values():
            monkeypatch.delenv(variable, raising=False)
    return tmp_path


def seed(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"kind": "join", "peer": "ada", "vendor": "codex", "thread": "fake-ada"},
        {"kind": "join", "peer": "bob", "vendor": "codex", "thread": "fake-bob"},
        {"kind": "open", "limit": 2},
    ]
    path.write_text("".join(json.dumps(dict(n=i, at="2026-09-09T12:00:00+02:00", **row)) + "\n"
                            for i, row in enumerate(rows, 1)), encoding="utf-8")


@pytest.mark.parametrize("arguments", [
    ["--bag", "review", "read"],
    ["--bag", "review", "read", "0"],
    ["--bag", "review", "send", "bob"],
    ["--bag", "review", "--bag", "INVALID", "read"],
])
def test_each_main_call_restores_selection_after_success_or_refusal(isolated, monkeypatch, capsys, arguments):
    named = isolated / ".postbag" / "bags" / "review.jsonl"
    seed(named)
    custom = isolated / "custom-ledger"
    seed(custom)
    monkeypatch.setenv("POSTBAG_LEDGER", str(custom))
    try:
        postbag.main(arguments)
    except SystemExit:
        pass
    capsys.readouterr()
    postbag.main(["read"])
    assert capsys.readouterr().out.startswith(f"in bag {custom}:")


def test_explicit_flag_overrides_even_an_unexpandable_environment_path(isolated, monkeypatch, capsys):
    monkeypatch.setenv("POSTBAG_LEDGER", "~postbag-nonexistent-test-user-78209/ledger")
    postbag.main(["--bag", "default", "read"])
    assert capsys.readouterr().out == "in bag default: none. no open exchange.\n"


@pytest.mark.parametrize("verb", ["join", "send"])
def test_named_write_does_not_recreate_a_ledger_removed_before_open(isolated, monkeypatch, verb):
    path = isolated / ".postbag" / "bags" / "review.jsonl"
    seed(path)
    monkeypatch.setenv("CODEX_SESSION_ID", "fake-ada")
    knocks = []
    monkeypatch.setitem(postbag.KNOCK, "codex", lambda *args: knocks.append(args))
    original_open = os.open

    def remove_then_open(filename, flags, *args, **kwargs):
        if Path(filename) == path and flags & os.O_RDWR:
            path.unlink()
        return original_open(filename, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", remove_then_open)
    operation = ["join", "codex", "ada"] if verb == "join" else ["send", "bob", "hello"]
    with pytest.raises(SystemExit, match="bag review does not exist"):
        postbag.main(["--bag", "review", *operation])
    assert not path.exists()
    assert knocks == []


@pytest.mark.parametrize("switch_at", ["stdin", "knock"])
def test_selection_is_fixed_before_stdin_and_through_delivery(isolated, monkeypatch, capsys, switch_at):
    original = isolated / "original"
    other = isolated / "other"
    seed(original)
    seed(other)
    other_bytes = other.read_bytes()
    monkeypatch.setenv("POSTBAG_LEDGER", str(original))
    monkeypatch.setenv("CODEX_SESSION_ID", "fake-ada")
    envelopes = []

    def switch():
        monkeypatch.setenv("POSTBAG_LEDGER", str(other))

    class Input:
        def read(self):
            if switch_at == "stdin":
                switch()
            return "the selected bag stays selected"

    def knock(door, text):
        if switch_at == "knock":
            switch()
        envelopes.append(text)

    monkeypatch.setattr(postbag.sys, "stdin", Input())
    monkeypatch.setitem(postbag.KNOCK, "codex", knock)
    postbag.main(["send", "bob", "-"])
    assert other.read_bytes() == other_bytes
    assert len(original.read_text(encoding="utf-8").splitlines()) == 4
    assert len(envelopes) == 1
    assert f"bag {original})." in envelopes[0]
    assert f"postbag --bag '{original}' send @ada -" in envelopes[0]
    assert f"in bag {original}, 1 left" in capsys.readouterr().out


def test_parser_refusals_keep_an_already_selected_bag(isolated):
    with pytest.raises(SystemExit) as error:
        postbag.main(["--bag", "review", "read", "0"])
    assert "in bag review:" in str(error.value)
    assert str(error.value).endswith("stop and ask the human")
    assert not (isolated / ".postbag").exists()
