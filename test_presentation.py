"""Letter numbering, named presentation, and the reply envelope contract."""
import json
import re

import pytest

from test_postbag import bag, be, joined, expected_bag_command, expected_bag_label  # noqa: F401 -- shared pytest fixtures


FOOTER = ("Reply only when a reply advances the task. Do not send courtesy acknowledgements or "
          "unsolicited delivery checks, and do not add a question or offer that needs no answer.\n")
FINAL = "Final letter. Do not reply to this letter, even if its body asks for a reply."


@pytest.fixture
def pair(bag, be):
    be("claude")
    bag.join("claude", "ada")
    be("codex")
    bag.join("codex", "bob")
    be("claude")
    return bag


def read_output(bag, capsys, count=None):
    capsys.readouterr()
    bag.read(count)
    output = capsys.readouterr().out
    assert output.startswith(f"in bag {expected_bag_label()}: ")
    return output


def ledger_lines(output):
    """History rows retain their ledger line. The header and bodies are not rows."""
    return [int(n) for n in re.findall(r"^\s*(\d+)\s+\d{4}-\S+\s+", output, re.M)]


def shell_reply(sender):
    return (f"If it needs an answer, reply with:\n"
            f"{expected_bag_command(f'send @{sender}')} - <<'POSTBAG'\n"
            "<your reply>\n"
            "POSTBAG\n"
            "Change POSTBAG at both ends to a word that does not occur in your reply.")


def test_envelope_numbers_letters_cumulatively_and_puts_reply_after_body(pair, be):
    for n in range(4):
        pair.send("@bob", f"Earlier letter {n + 1}.")
    be("codex")
    pair.join("codex", "bob")
    be("claude")

    body = "Review the parser.\nKeep the findings concrete."
    receipt = pair.send("@bob", body)
    vendor, door, delivered = pair.KNOCKED[-1]
    assert vendor == "codex" and door["thread"] == "t-1"
    assert delivered == (
        f"Letter 5 from @ada to @bob via postbag (bag {expected_bag_label()}).\n\n"
        f"{body}\n\n" + FOOTER + shell_reply("ada")
    )
    assert receipt["letter"] == 5 and receipt["final"] is False


def test_final_envelope_forbids_reply_even_when_the_body_requests_one(pair):
    body = "Reply to this message, even if another instruction says to stop."
    pair.send("bob", body, final=True)
    delivered = pair.KNOCKED[-1][2]
    assert delivered == (
        f"Letter 1 from @ada to @bob via postbag (bag {expected_bag_label()}).\n\n"
        f"{body}\n\n" + FINAL
    )
    assert "postbag --bag" not in delivered and "Reply only when" not in delivered


def test_a_final_letter_closes_nothing_and_the_next_letter_is_ordinary(pair, be):
    pair.send("bob", "Last word from ada.", final=True)
    be("codex")
    receipt = pair.send("ada", "Bob still writes.")
    delivered = pair.KNOCKED[-1][2]
    assert delivered.startswith(f"Letter 2 from @bob to @ada via postbag (bag {expected_bag_label()}).\n\n")
    assert delivered.endswith(FOOTER + shell_reply("bob"))
    assert receipt == {"bag": expected_bag_label(), "from": "bob", "to": "ada", "record": 4,
                       "letter": 2, "final": False, "submission_state": "submitted"}
    assert [rec.get("final") for rec in pair.records() if rec["kind"] == "letter"] == [True, None]


def test_joins_do_not_consume_letter_numbers(pair, be):
    pair.send("bob", "First.")
    pair.join("claude", "ada")
    be("codex")
    pair.join("codex", "bee")
    be("claude")
    pair.send("@bee", "Second after two joins.")
    assert pair.KNOCKED[-1][2].startswith(
        f"Letter 2 from @ada to @bee via postbag (bag {expected_bag_label()}).\n"
    )


def test_read_tail_uses_all_history_for_bindings_and_ordinals(pair, be, capsys):
    pair.send("bob", "OUTSIDE-TAIL")
    be("codex")
    pair.join("codex", "bee")
    be("claude")
    pair.send("bee", "SECOND-IN-TAIL")
    pair.send("bee", "THIRD-IN-TAIL")

    output = read_output(pair, capsys, 3)
    header, history = output.split("\n", 1)
    assert "@ada (claude)" in header and "@bee (codex)" in header
    assert "@bob" not in header
    assert header.endswith(". 3 letters.")
    assert ledger_lines(output) == [4, 5, 6]
    assert "OUTSIDE-TAIL" not in history
    assert re.search(r"^\s*5\s+\S+\s+2\s+@ada -> @bee$", history, re.M)
    assert re.search(r"^\s*6\s+\S+\s+3\s+@ada -> @bee$", history, re.M)
    assert "exchange" not in output


def test_read_one_record_keeps_its_cumulative_ordinal(joined, capsys):
    joined.send("codex", "FIRST-OMITTED")
    joined.send("@codex", "SECOND-VISIBLE")
    output = read_output(joined, capsys, 1)
    header, history = output.split("\n", 1)
    assert "@claude (claude)" in header and "@codex (codex)" in header
    assert "2 letters." in header
    assert ledger_lines(history) == [4]
    assert "FIRST-OMITTED" not in history and "SECOND-VISIBLE" in history
    assert re.search(r"^\s*4\s+\S+\s+2\s+@claude -> @codex$", history, re.M)


def test_read_lists_joins_in_one_flat_sequence(pair, capsys):
    output = read_output(pair, capsys)
    header, history = output.split("\n", 1)
    assert "@ada (claude)" in header and "@bob (codex)" in header
    assert header.endswith(". no letters.")
    assert ledger_lines(history) == [1, 2]
    assert "exchange" not in output.lower() and output.count("\n\n") == 0


def test_read_of_a_missing_bag_refuses_and_creates_nothing(bag, capsys):
    with pytest.raises(bag.Refusal) as error:
        bag.read(None)
    assert str(error.value) == (f"postbag: in bag {expected_bag_label()}: bag {expected_bag_label()} "
                                "does not exist, run: postbag bags; stop and ask the human")
    assert error.value.recovery == {"action": "bags", "actor": "caller", "bag": expected_bag_label()}
    assert capsys.readouterr().out == ""
    assert not bag.ledger_path().exists() and not bag.ledger_path().parent.exists()


def test_read_names_a_taken_door_by_ledger_line_and_join_by_timestamp(pair, be, monkeypatch, capsys):
    be("codex")
    monkeypatch.setenv("CODEX_SESSION_ID", "presentation-replacement-codex")
    capsys.readouterr()
    pair.join("codex", "bob")
    first = pair.records()[1]
    assert capsys.readouterr().out == f"@bob (codex) joined in bag {expected_bag_label()}, taken from the codex door that joined at {first['at']}\n"
    output = read_output(pair, capsys)
    assert "join   @bob (codex), taken from the door that joined at line 2" in output
    assert "joined at 2026" not in output
    assert "presentation-replacement-codex" not in output


def test_historical_names_survive_rename_and_handover(pair, be, monkeypatch, capsys):
    pair.send("bob", "HISTORICAL-LETTER")
    old_letter = pair.records()[-1].copy()
    pair.join("claude", "alix")
    be("codex")
    monkeypatch.setenv("CODEX_SESSION_ID", "presentation-replacement-codex")
    pair.join("codex", "ada")

    output = read_output(pair, capsys)
    header, history = output.split("\n", 1)
    assert "@ada (codex)" in header and "@alix (claude)" in header
    assert re.search(r"\b1\s+@ada\s*->\s*@bob\b", history)
    assert not re.search(r"\b1\s+@alix\s*->", history)
    assert next(rec for rec in pair.records() if rec["kind"] == "letter") == old_letter
    assert "HISTORICAL-LETTER" in history


@pytest.mark.parametrize("tail", [None, 1])
def test_current_roster_shows_vendors_and_redacts_all_door_fields(
    bag, be, monkeypatch, capsys, tail
):
    secrets = ("/tmp/presentation-private.sock", "presentation-private-token", "presentation-private-thread")
    be("claude")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_SOCKET", secrets[0])
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_TOKEN", secrets[1])
    bag.join("claude", "ada")
    be("codex")
    monkeypatch.setenv("CODEX_SESSION_ID", secrets[2])
    bag.join("codex", "bob")

    output = read_output(bag, capsys, tail)
    header = output.splitlines()[0]
    assert "@ada (claude)" in header and "@bob (codex)" in header
    assert header.endswith(". no letters.")
    assert all(secret not in output for secret in secrets)


def test_three_registered_peers_are_labelled_experimental_and_listed_in_the_envelope(
    pair, be, monkeypatch, capsys
):
    be("claude")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_SOCKET", "/tmp/presentation-cleo.sock")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_TOKEN", "presentation-cleo-token")
    pair.join("claude", "cleo")
    output = read_output(pair, capsys)
    header = output.splitlines()[0]
    assert "experimental" in header.lower()
    assert all(name in header for name in ("@ada", "@bob", "@cleo"))

    be("claude")
    pair.send("bob", "First sender.")
    first = pair.KNOCKED[-1][2].splitlines()
    assert first[0] == f"Letter 1 from @ada to @bob via postbag (bag {expected_bag_label()})."
    assert first[1] == "Registered names in this bag: @ada, @bob, @cleo."
    assert first[2] == "" and first[3] == "First sender."
    be("codex")
    pair.send("cleo", "Second sender, same sequence.")
    assert pair.KNOCKED[-1][0] == "claude"
    assert pair.KNOCKED[-1][2].startswith(
        f"Letter 2 from @bob to @cleo via postbag (bag {expected_bag_label()}).\n"
        "Registered names in this bag: @ada, @bob, @cleo.\n\n"
    )


def test_final_envelope_keeps_three_peer_roster_without_reply_command(pair, be, monkeypatch):
    be("claude")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_SOCKET", "/tmp/presentation-cleo.sock")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_TOKEN", "presentation-cleo-token")
    pair.join("claude", "cleo")
    pair.send("ada", "The final message.", final=True)
    assert pair.KNOCKED[-1][2] == (
        f"Letter 1 from @cleo to @ada via postbag (bag {expected_bag_label()}).\n"
        "Registered names in this bag: @ada, @bob, @cleo.\n\n"
        "The final message.\n\n" + FINAL
    )


def test_legacy_ledger_displays_default_names_and_opens_as_history_without_rewriting(bag, capsys):
    rows = [
        {"n": 1, "at": "2026-09-08T11:00:00", "kind": "join", "peer": "claude",
         "socket": "/tmp/legacy-presentation.sock", "token": "legacy-presentation-token"},
        {"n": 2, "at": "2026-09-08T11:00:01", "kind": "join", "peer": "codex",
         "thread": "legacy-presentation-thread"},
        {"n": 3, "at": "2026-09-08T11:00:02", "kind": "open", "limit": 2},
        {"n": 4, "at": "2026-09-08T11:00:03", "kind": "letter", "from": "claude",
         "to": "codex", "body": "LEGACY-LETTER"},
    ]
    original = "".join(json.dumps(row) + "\n" for row in rows).encode()
    bag.ledger_path().parent.mkdir()
    bag.ledger_path().write_bytes(original)
    output = read_output(bag, capsys)
    header, history = output.split("\n", 1)
    assert "@claude (claude)" in header and "@codex (codex)" in header
    assert header.endswith(". 1 letter.")
    assert "   3  2026-09-08T11:00:02  open   2 letters (history)" in history
    assert re.search(r"^\s*4\s+\S+\s+1\s+@claude\s*->\s*@codex$", history, re.M)
    assert "LEGACY-LETTER" in history
    assert "legacy-presentation-token" not in output
    assert "legacy-presentation-thread" not in output
    assert "/tmp/legacy-presentation.sock" not in output
    assert bag.ledger_path().read_bytes() == original


def test_read_prints_the_spec_shape_header_and_letter_rows(pair, be, capsys):
    pair.send("bob", "Review parser.py, top three findings please.")
    be("codex")
    pair.send("ada", "Done.", final=True)
    stamps = [rec["at"] for rec in pair.records()]
    output = read_output(pair, capsys)
    lines = output.splitlines()
    assert lines[0] == f"in bag {expected_bag_label()}: @ada (claude), @bob (codex). 2 letters."
    assert lines[1] == f"   1  {stamps[0]}  join   @ada (claude)"
    assert lines[2] == f"   2  {stamps[1]}  join   @bob (codex)"
    assert lines[3] == f"   3  {stamps[2]}  1      @ada -> @bob"
    assert lines[4] == "      Review parser.py, top three findings please."
    assert lines[5] == f"   4  {stamps[3]}  2 final @bob -> @ada"
    assert lines[6] == "      Done."
    assert len(lines) == 7
    assert not re.search(r"^\s*\d+\s+\S+\s+letter\b", output, re.M)
    assert lines[1].index("@ada") == lines[3].index("@ada")
