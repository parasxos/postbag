"""postbag 2.1: leave, a recorded withdrawal. Every native door is faked."""
import fcntl
import json
import os
import stat

import pytest

import postbag
from test_core_2 import selections
from test_hardening import SCRIPT, cli, fake_codex, prepare_pair, rows  # noqa: F401 -- subprocess fixture with a private ledger
from test_names import session  # noqa: F401
from test_postbag import bag, be, joined, expected_bag_command, expected_bag_label  # noqa: F401


def refusal(operation):
    with pytest.raises(postbag.Refusal) as error:
        operation()
    assert str(error.value).count(";") == 1 and str(error.value).endswith("; stop and ask the human")
    return error.value


def kinds(bag):
    return [rec["kind"] for rec in bag.records()]


def read_recovery():
    return {"action": "read", "actor": "caller", "bag": expected_bag_label()}


# the record, the receipt and the bindings --------------------------------------

def test_leave_appends_the_door_as_its_join_recorded_it_and_removes_the_binding(joined, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "11111111-2222-3333-4444-555555555555")  # navigation metadata, not a door
    before = joined.records()
    receipt = joined.leave()
    rec = joined.records()[-1]
    assert rec == {"n": 3, "at": rec["at"], "kind": "leave", "peer": "claude", "vendor": "claude",
                   "socket": "/tmp/x.sock", "token": "tok"}
    assert "session_id" not in rec
    assert receipt == {"bag": expected_bag_label(), "name": "claude", "vendor": "claude", "record": 3}
    assert capsys.readouterr().out == f"@claude (claude) left bag {expected_bag_label()}\n"
    assert joined.records()[:2] == before  # history is never rewritten
    state = joined.Snapshot(joined.records())
    assert set(state.peers) == {"codex"}
    assert state.history[-1] == (rec, None, ([], None))
    assert state.left("claude") == rec and state.left("codex") is None
    assert joined.KNOCKED == []  # no door was contacted


def test_a_codex_leave_carries_the_thread(bag, be):
    be("codex")
    bag.join("codex")
    receipt = bag.leave()
    rec = bag.records()[-1]
    assert rec == {"n": 2, "at": rec["at"], "kind": "leave", "peer": "codex", "vendor": "codex", "thread": "t-1"}
    assert receipt == {"bag": expected_bag_label(), "name": "codex", "vendor": "codex", "record": 2}
    assert bag.Snapshot(bag.records()).peers == {}


def test_a_send_to_a_left_name_refuses_with_when_it_left(joined, be):
    joined.leave()
    left = joined.records()[-1]
    be("codex")
    error = refusal(lambda: joined.send("claude", "anyone home"))
    assert str(error) == (f"postbag: in bag {expected_bag_label()}: @claude is not registered, it left this bag at "
                          f"{left['at']}, run {expected_bag_command('read')}; stop and ask the human")
    assert error.recovery == read_recovery()
    assert joined.KNOCKED == [] and kinds(joined) == ["join", "join", "leave"]


def test_the_left_door_cannot_send_and_is_not_told_to_rejoin(joined):
    """An old queued letter that wakes a departed door must not talk it back in."""
    joined.leave()
    left = joined.records()[-1]
    error = refusal(lambda: joined.send("codex", "from a door that left"))
    assert str(error) == (f"postbag: in bag {expected_bag_label()}: your name @claude left this bag at {left['at']}, "
                          "do not join again unless the human asks you to resume; stop and ask the human")
    assert "left this bag at" in str(error) and "do not join again" in str(error)
    assert error.recovery == read_recovery()
    assert joined.KNOCKED == [] and kinds(joined) == ["join", "join", "leave"]


def test_a_door_whose_join_carried_a_session_id_still_leaves(bag, be, monkeypatch):
    be("claude")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "11111111-2222-3333-4444-555555555555")
    bag.join("claude", "ada")
    assert bag.records()[-1]["session_id"] == "11111111-2222-3333-4444-555555555555"
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "99999999-2222-3333-4444-555555555555")  # a new conversation, same inbox
    assert bag.leave()["name"] == "ada"
    rec = bag.records()[-1]
    assert rec["kind"] == "leave" and "session_id" not in rec
    assert bag.Snapshot(bag.records()).peers == {}


@pytest.mark.parametrize("again", ["claude", "ada"])
def test_join_after_leave_restores_a_binding_under_the_same_or_another_name(joined, be, again):
    joined.leave()
    receipt = joined.join("claude", again)
    assert receipt == {"bag": expected_bag_label(), "name": again, "vendor": "claude", "renamed": None, "took": None}
    assert joined.send("codex", "back")["letter"] == 1
    be("codex")
    assert joined.send(again, "welcome back")["to"] == again
    assert joined.KNOCKED[-1][1]["token"] == "tok"
    assert kinds(joined) == ["join", "join", "leave", "join", "letter", "letter"]


def test_a_repeated_leave_refuses_and_appends_nothing(joined):
    joined.leave()
    before = joined.ledger_path().read_bytes()
    error = refusal(joined.leave)
    assert str(error) == (f"postbag: in bag {expected_bag_label()}: this door holds no name in bag {expected_bag_label()}, "
                          f"run {expected_bag_command('read')}; stop and ask the human")
    assert error.recovery == read_recovery()
    assert "join" not in str(error).replace("in bag", "")  # never advise join in order to leave
    assert joined.ledger_path().read_bytes() == before


def test_leave_from_a_terminal_refuses(joined, be):
    be(None)
    before = joined.ledger_path().read_bytes()
    error = refusal(joined.leave)
    assert "leave is a peer's verb, run it inside a claude or codex session" in str(error)
    assert error.recovery is None
    assert joined.ledger_path().read_bytes() == before


def test_leave_by_a_door_that_never_joined_refuses_with_read(bag, be, monkeypatch):
    be("codex")
    bag.join("codex")
    be("claude")
    before = bag.ledger_path().read_bytes()
    error = refusal(bag.leave)
    assert f"this door holds no name in bag {expected_bag_label()}, run {expected_bag_command('read')}" in str(error)
    assert error.recovery == read_recovery()
    assert bag.ledger_path().read_bytes() == before
    # a door whose name was taken holds nothing either, and hears the same
    monkeypatch.setenv("CODEX_SESSION_ID", "t-9")
    be("codex")
    monkeypatch.setenv("CODEX_SESSION_ID", "t-9")
    bag.join("codex")  # took @codex from t-1
    monkeypatch.setenv("CODEX_SESSION_ID", "t-1")
    error = refusal(bag.leave)
    assert "this door holds no name" in str(error) and error.recovery == read_recovery()
    assert kinds(bag) == ["join", "join"]


def test_leave_from_a_shell_matching_two_names_refuses(bag, session, monkeypatch):
    ada = session("codex", "one")
    bag.join("codex", "ada")
    session("claude", "two")
    bag.join("claude", "bob")
    monkeypatch.setenv("CODEX_SESSION_ID", ada["thread"])
    error = refusal(bag.leave)
    assert "this shell matches multiple registered names, leave from one session" in str(error)
    assert kinds(bag) == ["join", "join"]


# missing bags, locks and modes --------------------------------------------------

@pytest.mark.parametrize("case", ["default", "named", "path", "environment"])
def test_leave_on_a_missing_bag_creates_nothing_and_points_to_bags(bag, be, tmp_path, monkeypatch, capsys, case):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("POSTBAG_LEDGER")
    (tmp_path / "home").mkdir()
    select, extra, path, label = selections(tmp_path)[case]
    for variable, value in extra.items():
        monkeypatch.setenv(variable, value)
    be("claude")
    error = refusal(lambda: bag.main([*select, "leave"]))
    assert error.recovery == {"action": "bags", "actor": "caller", "bag": label}
    assert str(error) == f"postbag: in bag {label}: bag {label} does not exist, run: postbag bags; stop and ask the human"
    assert "join" not in str(error)
    assert capsys.readouterr().out == ""
    assert not path.exists() and not path.parent.exists()


def test_leave_refuses_a_busy_ledger_before_reading_it(joined):
    before = joined.ledger_path().read_bytes()
    with joined.ledger_path().open("r+") as holder:
        fcntl.flock(holder, fcntl.LOCK_EX)  # a send that took the lock first finishes before the leave is recorded
        error = refusal(lambda: joined.leave(wait=False))
    assert error.error_code == "ledger_busy" and error.submission_state == "not_submitted"
    assert error.recovery == read_recovery()
    assert "the ledger is busy" in str(error)
    assert joined.ledger_path().read_bytes() == before
    assert joined.leave()["record"] == 3  # the lock is gone, the leave lands


def test_a_leave_recorded_first_makes_the_next_send_to_that_name_refuse(joined, be):
    joined.leave()
    be("codex")
    error = refusal(lambda: joined.send("claude", "too late"))
    assert "it left this bag at" in str(error)
    assert joined.KNOCKED == []


def test_leave_refuses_an_exposed_ledger_without_changing_it(joined):
    path = joined.ledger_path()
    path.chmod(0o644)
    before = path.read_bytes()
    error = refusal(joined.leave)
    assert "the ledger grants other users access, fix its mode to 0600" in str(error)
    assert stat.S_IMODE(path.stat().st_mode) == 0o644 and path.read_bytes() == before


def test_a_failed_fsync_after_the_leave_append_reports_the_record_as_unconfirmed(joined, monkeypatch):
    """ledger()'s write lambda writes, flushes, then fsyncs. When the fsync raises, the line is already
    in the file: the refusal says the leave could not be confirmed and sends the caller to read."""
    def denied(fd):
        raise OSError(5, "Input/output error")

    real = os.fsync
    monkeypatch.setattr(postbag.os, "fsync", denied)
    error = refusal(joined.leave)
    assert error.error_code == "recording_failed" and error.submission_state == "not_submitted"
    assert str(error) == (f"postbag: in bag {expected_bag_label()}: @claude's leave could not be confirmed in bag "
                          f"{expected_bag_label()} ([Errno 5] Input/output error), read the bag before leaving again"
                          "; stop and ask the human")
    assert error.recovery == read_recovery()
    monkeypatch.setattr(postbag.os, "fsync", real)
    assert kinds(joined) == ["join", "join", "leave"]  # observed: the flushed line is there, only its durability was unconfirmed
    assert set(joined.Snapshot(joined.records()).peers) == {"codex"}


# an inconsistent leave is not a ledger ----------------------------------------

def write_rows(bag, *recs):
    bag.ledger_path().parent.mkdir(parents=True, exist_ok=True)
    stamped = [{"n": n, "at": f"2026-10-01T10:00:{n:02d}+02:00", **rec} for n, rec in enumerate(recs, 1)]
    text = "".join(json.dumps(rec) + "\n" for rec in stamped)
    bag.ledger_path().write_text(text, encoding="utf-8")
    bag.ledger_path().chmod(0o600)
    return text


ADA = {"kind": "join", "peer": "ada", "vendor": "claude", "socket": "/tmp/x.sock", "token": "tok"}
BOB = {"kind": "join", "peer": "bob", "vendor": "codex", "thread": "t-1"}


@pytest.mark.parametrize("stray, who", [
    ({"kind": "leave", "peer": "ada", "vendor": "codex", "thread": "t-1"}, "ada"),       # bob's door leaves ada
    ({"kind": "leave", "peer": "zed", "vendor": "codex", "thread": "t-1"}, "zed"),       # a name nobody holds
    ({"kind": "leave", "peer": "ada", "vendor": "claude", "socket": "/tmp/x.sock", "token": "old"}, "ada"),  # a stale door
], ids=["held-by-another-door", "held-by-nobody", "stale-door-fields"])
def test_a_leave_the_door_does_not_hold_makes_read_send_and_bags_refuse(bag, be, tmp_path, monkeypatch, stray, who):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    original = write_rows(bag, ADA, BOB, stray)
    expected = f"ledger line 3 leaves @{who}, which that door does not hold ({bag.ledger_path()})"
    assert expected in str(refusal(lambda: bag.read(None)))
    be("codex")
    assert expected in str(refusal(lambda: bag.send("ada", "x")))
    assert expected in str(refusal(bag.leave))
    be("claude")
    assert expected in str(refusal(lambda: bag.join("claude", "ada")))
    listed, counts, _, problems = bag.inventory()
    assert listed == [(expected_bag_label(), None, "-", None)]
    assert counts == {"letters": 0, "empty": 0, "unavailable": 1}
    assert len(problems) == 1 and expected in problems[0]
    assert bag.KNOCKED == [] and bag.ledger_path().read_text(encoding="utf-8") == original


def test_a_stale_leave_by_the_old_holder_never_unregisters_the_taker(bag, be):
    """After a takeover, a leave written with the old holder's fields replays as inconsistent: the bag
    refuses rather than applying it, so the taker's binding is never silently withdrawn."""
    taker = {"kind": "join", "peer": "ada", "vendor": "claude", "socket": "/tmp/y.sock", "token": "new"}
    original = write_rows(bag, ADA, BOB, taker)
    assert bag.Snapshot(bag.records()).peers["ada"]["token"] == "new"
    original = write_rows(bag, ADA, BOB, taker, {**ADA, "kind": "leave"})
    expected = f"ledger line 4 leaves @ada, which that door does not hold ({bag.ledger_path()})"
    assert expected in str(refusal(lambda: bag.read(None)))
    be("codex")
    assert expected in str(refusal(lambda: bag.send("ada", "x")))
    assert bag.KNOCKED == [] and bag.ledger_path().read_text(encoding="utf-8") == original


def test_a_leave_after_a_rename_is_inconsistent_even_with_the_right_door(bag):
    """A door that renamed no longer holds its old name, so a stale leave of it cannot replay."""
    write_rows(bag, ADA, {**ADA, "peer": "bee"}, {**ADA, "kind": "leave"})
    assert "ledger line 3 leaves @ada, which that door does not hold" in str(refusal(lambda: bag.read(None)))


@pytest.mark.parametrize("line", [
    {"kind": "leave", "peer": "Ada", "vendor": "claude", "socket": "/s", "token": "t"},   # invalid name
    {"kind": "leave", "peer": "ada", "vendor": "gemini", "thread": "t"},                   # unknown vendor
    {"kind": "leave", "peer": "codex", "vendor": "claude", "socket": "/s", "token": "t"},  # reserved name, other vendor
    {"kind": "leave", "peer": "ada", "vendor": "claude", "socket": "/s"},                  # a door field missing
    {"kind": "leave", "peer": "ada", "vendor": "codex", "thread": ""},                     # an empty door field
    {"kind": "leave", "peer": "ada"},                                                      # no door at all
    {"kind": "leave", "peer": "codex", "thread": "t-1"},                                   # no vendor: only old joins may omit it
    {"kind": "leave", "peer": "claude", "socket": "/s", "token": "t"},                     # no vendor, claude fields
])
def test_a_leave_of_the_wrong_shape_is_not_a_record(bag, line):
    write_rows(bag, line)
    assert "ledger line 1 is not a record" in str(refusal(bag.records))


def test_a_leave_without_vendor_is_not_a_record_while_a_legacy_join_still_is(bag, be):
    original = write_rows(bag,
                          {"kind": "join", "peer": "codex", "thread": "t-1"},  # legacy join, vendor implied
                          {"kind": "leave", "peer": "codex", "thread": "t-1"})
    error = refusal(lambda: bag.read(None))
    assert f"ledger line 2 is not a record ({bag.ledger_path()})" in str(error)
    be("codex")
    assert "ledger line 2 is not a record" in str(refusal(bag.leave))
    assert bag.ledger_path().read_text(encoding="utf-8") == original
    write_rows(bag, {"kind": "join", "peer": "codex", "thread": "t-1"})
    assert bag.door("codex")["thread"] == "t-1"


# what a name's history says -----------------------------------------------------

def test_a_door_that_left_and_rejoined_under_another_name_is_pointed_to(bag, session):
    session("claude", "one")
    bag.join("claude", "ada")
    session("codex", "two")
    bag.join("codex", "bob")
    session("claude", "one")
    bag.leave()
    bag.join("claude", "bee")
    session("codex", "two")
    error = refusal(lambda: bag.send("ada", "old address"))
    assert f"@ada is not registered, its last door now holds @bee, run {expected_bag_command('read')}" in str(error)
    assert "left this bag" not in str(error) and error.recovery == read_recovery()
    assert bag.send("bee", "new address")["to"] == "bee"


def test_a_rename_after_a_leave_and_rejoin_mentions_only_the_new_name(bag, session):
    session("claude", "one")
    bag.join("claude", "ada")
    session("codex", "two")
    bag.join("codex", "bob")
    session("claude", "one")
    bag.leave()
    bag.join("claude", "ada")
    bag.join("claude", "cee")
    session("codex", "two")
    error = refusal(lambda: bag.send("ada", "old address"))
    assert "@ada is not registered, its last door now holds @cee" in str(error)
    assert "left this bag" not in str(error)


def test_a_displaced_sender_whose_taker_left_hears_taken_never_left(bag, session):
    session("codex", "one")
    bag.join("codex", "ada")
    session("claude", "two")
    bag.join("claude", "bob")
    session("codex", "three")
    bag.join("codex", "ada")  # took ada from door one
    bag.leave()
    gone = bag.records()[-1]
    taker = bag.records()[-2]
    session("codex", "one")
    error = refusal(lambda: bag.send("bob", "displaced"))
    assert (f"your name @ada was taken by the codex door that joined at {taker['at']}, "
            f"which left this bag at {gone['at']}") in str(error)
    assert "your name @ada left" not in str(error) and "join again" not in str(error)
    assert error.recovery == {"action": "join", "actor": "caller", "bag": expected_bag_label(), "vendor": "codex", "name": None}
    session("claude", "two")
    error = refusal(lambda: bag.send("ada", "to a name nobody holds"))
    assert f"@ada is not registered, it left this bag at {gone['at']}" in str(error)
    assert bag.KNOCKED == []


def test_a_door_that_left_then_lost_a_later_name_hears_about_that_name(bag, session):
    session("codex", "one")
    bag.join("codex", "ada")
    session("claude", "two")
    bag.join("claude", "bob")
    session("codex", "one")
    bag.leave()
    bag.join("codex", "cleo")
    session("codex", "three")
    bag.join("codex", "cleo")  # took cleo
    session("codex", "one")
    error = refusal(lambda: bag.send("bob", "displaced"))
    assert "your name @cleo was taken by the codex door that joined at" in str(error)
    assert "left this bag" not in str(error)


# the rest of the bag is untouched -----------------------------------------------

def test_leave_changes_neither_the_letter_count_nor_record_numbers(joined, be, capsys):
    joined.send("codex", "one")
    be("codex")
    joined.send("claude", "two")
    joined.leave()
    state = joined.Snapshot(joined.records())
    assert state.letters == 2 and set(state.peers) == {"claude"}
    assert [rec["n"] for rec in joined.records()] == [1, 2, 3, 4, 5]
    assert [letter for _, letter, _ in state.history] == [None, None, 1, 2, None]
    be("claude")
    error = refusal(lambda: joined.send("codex", "three"))
    assert "it left this bag at" in str(error)
    be("codex")
    joined.join("codex")
    receipt = joined.send("claude", "three")
    assert (receipt["letter"], receipt["record"]) == (3, 7)
    assert joined.KNOCKED[-1][2].startswith("Letter 3 from @codex to @claude")
    capsys.readouterr()
    joined.read(2)
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"in bag {expected_bag_label()}: @claude (claude), @codex (codex). 3 letters."
    assert out[1].endswith("  join   @codex (codex)") and out[2].endswith("  3      @codex -> @claude")


def test_leave_in_one_bag_leaves_another_untouched(bag, be, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("POSTBAG_LEDGER")
    be("claude")
    bag.main(["join", "claude", "ada"])
    bag.main(["--bag", "review", "join", "claude", "ada"])
    be("codex")
    bag.main(["--bag", "review", "join", "codex", "bob"])
    be("claude")
    bag.main(["--bag", "review", "leave"])
    listed, counts, resumptions, problems = bag.inventory()
    assert problems == [] and counts == {"letters": 0, "empty": 2, "unavailable": 0}
    assert listed == [("default", 0, "-", [("ada", "claude")]), ("review", 0, "-", [("bob", "codex")])]
    assert [r["kind"] for r in rows(tmp_path / "home" / ".postbag" / "ledger.jsonl")] == ["join"]
    assert [r["kind"] for r in rows(tmp_path / "home" / ".postbag" / "bags" / "review.jsonl")] == ["join", "join", "leave"]
    bag.main(["leave"])  # the default bag still holds this door's name, so leaving it there is ordinary
    assert [r["kind"] for r in rows(tmp_path / "home" / ".postbag" / "ledger.jsonl")] == ["join", "leave"]


def test_read_prints_a_leave_row_and_drops_the_name_from_the_header(joined, capsys):
    joined.leave()
    capsys.readouterr()
    joined.read(None)
    out = capsys.readouterr().out.splitlines()
    left = joined.records()[-1]
    assert out[0] == f"in bag {expected_bag_label()}: @codex (codex). no letters."
    assert out[1].endswith("  join   @claude (claude)")
    assert out[3] == f"   3  {left['at']}  leave  @claude (claude)"
    assert "tok" not in "\n".join(out)


def test_a_left_claude_peer_has_no_resume_command_and_no_inventory_row_entry(bag, be, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("POSTBAG_LEDGER")
    be("claude")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "11111111-2222-3333-4444-555555555555")
    bag.main(["join", "claude", "ada"])
    be("codex")
    bag.main(["join", "codex", "bob"])
    listed, _, resumptions, _ = bag.inventory()
    assert listed == [("default", 0, "-", [("ada", "claude"), ("bob", "codex")])]
    assert resumptions == {"default": [("ada", "11111111-2222-3333-4444-555555555555")]}
    be("claude")
    bag.main(["leave"])
    listed, counts, resumptions, problems = bag.inventory()
    assert problems == [] and counts == {"letters": 0, "empty": 1, "unavailable": 0}
    assert listed == [("default", 0, "-", [("bob", "codex")])]
    assert resumptions == {"default": []}


def test_the_roster_line_disappears_when_the_third_name_leaves(bag, session):
    session("claude", "one")
    bag.join("claude", "ada")
    session("codex", "two")
    bag.join("codex", "bob")
    session("codex", "three")
    bag.join("codex", "cleo")
    session("claude", "one")
    bag.send("bob", "with a roster")
    assert "\nRegistered names in this bag: @ada, @bob, @cleo.\n" in bag.KNOCKED[-1][2]
    session("codex", "three")
    bag.leave()
    session("claude", "one")
    bag.send("bob", "without one")
    assert "Registered names" not in bag.KNOCKED[-1][2]
    assert bag.KNOCKED[-1][2].startswith(f"Letter 2 from @ada to @bob via postbag (bag {expected_bag_label()}).\n\nwithout one")


def test_a_legacy_ledger_with_opens_and_a_leave_reads_in_this_version(bag, capsys):
    write_rows(bag,
               {"kind": "join", "peer": "claude", "socket": "/tmp/x.sock", "token": "tok"},
               {"kind": "join", "peer": "codex", "thread": "t-1"},
               {"kind": "open", "limit": 2},
               {"kind": "letter", "from": "claude", "to": "codex", "body": "hi"},
               {"kind": "leave", "peer": "claude", "vendor": "claude", "socket": "/tmp/x.sock", "token": "tok"},
               {"kind": "leave", "peer": "codex", "vendor": "codex", "thread": "t-1"})  # leaves of legacy doors spell out the vendor
    bag.read(None)
    out = capsys.readouterr().out
    assert out.startswith(f"in bag {expected_bag_label()}: none. 1 letter.\n")
    assert "open   2 letters (history)" in out
    assert "leave  @claude (claude)" in out and "leave  @codex (codex)" in out
    assert bag.Snapshot(bag.records()).peers == {}


# the command line -----------------------------------------------------------------

def test_cli_leave_takes_no_arguments_and_removes_the_one_name_the_door_holds(cli, fake_codex):
    prepare_pair(cli)
    assert cli("join", "claude", "ada", peer="claude").returncode == 0  # the same claude door: one door, one name
    assert [r["peer"] for r in rows(cli.ledger) if r["kind"] == "join"] == ["claude", "codex", "ada"]
    result = cli("leave", peer="claude")
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"@ada (claude) left bag {cli.ledger}\n" and result.stderr == ""
    last = rows(cli.ledger)[-1]
    assert (last["n"], last["kind"], last["peer"], last["vendor"]) == (4, "leave", "ada", "claude")
    assert last["socket"] == "/tmp/postbag-test-unused.sock" and last["token"] == "test-token-not-a-credential"
    read = cli("read")
    assert read.returncode == 0 and read.stdout.startswith(f"in bag {cli.ledger}: @codex (codex). no letters.\n")
    assert f"  leave  @ada (claude)" in read.stdout
    refused = cli("send", "ada", "gone", peer="codex", extra=fake_codex)
    assert refused.returncode == 1 and "@ada is not registered, it left this bag at" in refused.stderr
    assert not os.path.exists(fake_codex["POSTBAG_TEST_CAPTURE"])
    again = cli("leave", peer="claude")
    assert again.returncode == 1 and "this door holds no name in bag" in again.stderr
    assert again.stderr.rstrip("\n").endswith("; stop and ask the human") and "Traceback" not in again.stderr
    assert len(rows(cli.ledger)) == 4


def test_cli_leave_refuses_arguments_and_a_terminal(cli):
    prepare_pair(cli)
    before = cli.ledger.read_bytes()
    extra = cli("leave", "ada", peer="claude")
    assert extra.returncode == 1 and "unrecognized arguments: ada" in extra.stderr
    terminal = cli("leave")
    assert terminal.returncode == 1 and "leave is a peer's verb" in terminal.stderr
    for result in (extra, terminal):
        assert result.stderr.rstrip("\n").endswith("; stop and ask the human") and "Traceback" not in result.stderr
    assert cli.ledger.read_bytes() == before


def test_leave_help_is_not_a_refusal_and_the_verb_is_listed(cli):
    result = cli("leave", "--help")
    assert result.returncode == 0 and "withdraw" in result.stdout and "stop and ask" not in result.stdout
    assert "leave" in cli("--help").stdout
    assert not cli.ledger.exists()
