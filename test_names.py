"""Named-session identity contracts. Every native door is faked."""

import json

import pytest

from test_postbag import bag


@pytest.fixture
def session(bag, monkeypatch):
    """Select a wholly fake vendor session, clearing both inherited identities."""
    def select(vendor=None, identity="one", **changes):
        for fields in bag.SESSION.values():
            for variable in fields.values():
                monkeypatch.delenv(variable, raising=False)
        if vendor is None:
            return {}
        fields = (
            {"socket": f"/tmp/postbag-test-{identity}.sock", "token": f"fake-token-{identity}"}
            if vendor == "claude" else {"thread": f"fake-thread-{identity}"}
        )
        fields.update(changes)
        for field, variable in bag.SESSION[vendor].items():
            monkeypatch.setenv(variable, fields[field])
        return fields

    select()
    return select


def register(bag, session, vendor, identity, name):
    fields = session(vendor, identity)
    bag.join(vendor, name)
    return fields


def exchange(bag, session, limit=5):
    session()
    bag.open_exchange(limit)


def refused_without_effect(bag, operation):
    before = bag.records()
    budget = bag.budget()
    knocks = len(bag.KNOCKED)
    with pytest.raises(SystemExit) as error:
        operation()
    assert "stop and ask the human" in str(error.value)
    assert bag.records() == before
    assert bag.budget() == budget
    assert len(bag.KNOCKED) == knocks
    return str(error.value)


@pytest.mark.parametrize("vendor", ["claude", "codex"])
def test_same_vendor_pair_routes_both_ways_by_name(bag, session, vendor):
    ada = register(bag, session, vendor, "one", "ada")
    bob = register(bag, session, vendor, "two", "bob")
    exchange(bag, session)

    session(vendor, "one")
    bag.send("@bob", "first letter")
    session(vendor, "two")
    bag.send("ada", "reply")

    assert [(r["from"], r["to"]) for r in bag.records() if r["kind"] == "letter"] == [
        ("ada", "bob"), ("bob", "ada"),
    ]
    assert [knock[0] for knock in bag.KNOCKED] == [vendor, vendor]
    for (_, door, _), expected in zip(bag.KNOCKED, [bob, ada]):
        assert door["vendor"] == vendor
        assert all(door[field] == value for field, value in expected.items())


def test_rename_releases_old_name_and_points_recipient_to_new_name(bag, session, capsys):
    ada = register(bag, session, "codex", "one", "ada")
    register(bag, session, "codex", "two", "bob")
    exchange(bag, session)
    session("codex", "one")
    capsys.readouterr()
    bag.join("codex", "cleo")
    announcement = capsys.readouterr().out
    assert announcement == "@cleo (codex) joined; renamed from @ada\n"
    assert bag.door("cleo")["thread"] == ada["thread"]
    refused_without_effect(bag, lambda: bag.door("ada"))

    session("codex", "two")
    error = refused_without_effect(bag, lambda: bag.send("@ada", "old address"))
    assert "@cleo" in error and "read" in error
    bag.send("cleo", "new address")
    assert bag.records()[-1]["to"] == "cleo"
    assert bag.records()[0]["peer"] == "ada"  # History is never rewritten.


def test_name_takeover_displaces_sender_and_reroutes_replies(bag, session, capsys):
    register(bag, session, "codex", "one", "ada")
    register(bag, session, "claude", "two", "bob")
    exchange(bag, session)
    session("codex", "one")
    bag.send("bob", "a question before the handover")
    capsys.readouterr()
    replacement = register(bag, session, "codex", "three", "ada")
    first = bag.records()[0]
    assert capsys.readouterr().out == f"@ada (codex) joined; taken from the codex door that joined at {first['at']}\n"

    session("codex", "one")
    error = refused_without_effect(bag, lambda: bag.send("bob", "displaced sender"))
    taker = bag.records()[-1]
    assert f"your name @ada was taken by the codex door that joined at {taker['at']}" in error
    assert taker["thread"] not in error and "line" not in error
    session("claude", "two")
    bag.send("@ada", "reply to the current holder")
    assert bag.KNOCKED[-1][1]["thread"] == replacement["thread"]
    assert bag.records()[-1]["to"] == "ada"


def test_released_bindings_never_revive_after_rename_and_takeover(bag, session):
    register(bag, session, "codex", "one", "ada")
    register(bag, session, "codex", "one", "bob")
    register(bag, session, "codex", "two", "bob")
    current = register(bag, session, "codex", "two", "cleo")
    exchange(bag, session)

    assert bag.door("cleo")["thread"] == current["thread"]
    for released in ("ada", "bob"):
        refused_without_effect(bag, lambda name=released: bag.door(name))
    session("codex", "one")
    error = refused_without_effect(bag, lambda: bag.send("cleo", "no resurrected identity"))
    assert "your name @bob was released when its taker renamed to @cleo" in error

    replacement = register(bag, session, "codex", "three", "ada")
    session("codex", "two")
    bag.send("ada", "new holder of a released address")
    assert bag.KNOCKED[-1][1]["thread"] == replacement["thread"]
    session("codex", "one")
    refused_without_effect(bag, lambda: bag.send("cleo", "still displaced"))


def test_rename_into_an_occupied_name_releases_both_previous_bindings(bag, session):
    original = register(bag, session, "codex", "one", "ada")
    register(bag, session, "codex", "two", "bob")
    register(bag, session, "claude", "three", "cleo")
    exchange(bag, session)
    session("codex", "one")
    bag.join("codex", "bob")

    assert bag.door("bob")["thread"] == original["thread"]
    refused_without_effect(bag, lambda: bag.door("ada"))
    session("codex", "two")
    refused_without_effect(bag, lambda: bag.send("cleo", "lost bob"))
    session("codex", "one")
    bag.send("cleo", "now bob")
    assert bag.records()[-1]["from"] == "bob"


def test_rejoining_the_same_binding_does_not_make_sender_ambiguous(bag, session):
    register(bag, session, "codex", "one", "ada")
    register(bag, session, "codex", "two", "bob")
    exchange(bag, session)
    session("codex", "one")
    for _ in range(3):
        bag.join("codex", "ada")
    bag.send("bob", "one current identity")
    assert bag.records()[-1]["from"] == "ada"
    assert len(bag.KNOCKED) == 1


@pytest.mark.parametrize("recipient", ["ada", "@ada"])
def test_send_to_own_name_is_a_refusal_without_spending(bag, session, recipient):
    register(bag, session, "codex", "one", "ada")
    exchange(bag, session)
    session("codex", "one")
    error = refused_without_effect(bag, lambda: bag.send(recipient, "self"))
    assert "@ada is your own name" in error


def test_sender_must_have_joined_even_with_complete_vendor_environment(bag, session):
    register(bag, session, "codex", "two", "bob")
    exchange(bag, session)
    session("codex", "one")
    error = refused_without_effect(bag, lambda: bag.send("bob", "not registered"))
    assert "this session has not joined, run postbag join codex" in error


def test_a_displaced_sender_whose_name_nobody_holds_learns_it_was_released(bag, session):
    register(bag, session, "codex", "one", "ada")
    register(bag, session, "claude", "two", "bob")
    taker = register(bag, session, "codex", "three", "ada")
    session("codex", "three", thread="fake-thread-four")
    bag.join("codex", "ada")  # the taker restarted: a new door, and the old taker holds nothing
    session("codex", "three", **taker)
    bag.join("codex", "dana")  # ... then rejoined under another name, so ada is held by the restart
    session("codex", "four")
    exchange(bag, session)
    session("codex", "one")
    error = refused_without_effect(bag, lambda: bag.send("bob", "displaced"))
    assert "your name @ada was taken by the codex door that joined at" in error

    session("codex", "three", thread="fake-thread-four")
    bag.join("codex", "erin")  # ada is now held by nobody, and its last holder is @erin
    session("codex", "one")
    error = refused_without_effect(bag, lambda: bag.send("bob", "displaced"))
    assert "your name @ada was released when its taker renamed to @erin" in error


def test_a_displaced_sender_hears_only_released_when_the_taker_holds_nothing(bag, session):
    register(bag, session, "codex", "one", "ada")
    register(bag, session, "claude", "two", "bob")
    register(bag, session, "codex", "three", "ada")   # took ada from door one
    register(bag, session, "codex", "three", "cleo")  # released ada
    register(bag, session, "codex", "four", "cleo")   # took cleo, so the taker of ada holds nothing
    exchange(bag, session)
    session("codex", "one")
    error = refused_without_effect(bag, lambda: bag.send("bob", "displaced"))
    assert "your name @ada was released; stop and ask the human" in error


def test_a_shell_inside_two_unjoined_sessions_is_told_both_joins(bag, session, monkeypatch):
    register(bag, session, "claude", "two", "bob")
    exchange(bag, session)
    session("codex", "one")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_SOCKET", "/tmp/postbag-test-nine.sock")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_TOKEN", "fake-token-nine")
    error = refused_without_effect(bag, lambda: bag.send("bob", "unjoined"))
    assert "run postbag join claude or postbag join codex" in error


def test_two_matching_vendor_identities_refuse_instead_of_picking_one(bag, session, monkeypatch):
    ada = register(bag, session, "codex", "one", "ada")
    register(bag, session, "claude", "two", "bob")
    register(bag, session, "codex", "three", "cleo")
    exchange(bag, session)
    session("claude", "two")
    monkeypatch.setenv("CODEX_SESSION_ID", ada["thread"])

    refused_without_effect(bag, lambda: bag.send("cleo", "ambiguous sender"))
    # Explicit vendor selection still allows join in a nested session.
    bag.join("codex", "dana")
    assert bag.door("dana")["thread"] == ada["thread"]
    refused_without_effect(bag, lambda: bag.door("ada"))
    refused_without_effect(bag, lambda: bag.send("cleo", "still two identities"))


def test_unregistered_other_vendor_environment_does_not_hide_the_one_match(bag, session, monkeypatch):
    register(bag, session, "codex", "one", "ada")
    register(bag, session, "codex", "two", "bob")
    exchange(bag, session)
    session("codex", "one")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_SOCKET", "/tmp/unregistered-postbag-test.sock")
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_TOKEN", "unregistered-fake-token")
    bag.send("bob", "only one registered match")
    assert bag.records()[-1]["from"] == "ada"


@pytest.mark.parametrize("vendor, field, replacement", [
    ("claude", "token", "fake-rotated-token"),
    ("claude", "socket", "/tmp/fake-rotated-socket.sock"),
    ("codex", "thread", "fake-rotated-thread"),
])
def test_changed_door_fields_require_rejoin_and_displace_old_identity(
    bag, session, vendor, field, replacement,
):
    register(bag, session, vendor, "one", "ada")
    register(bag, session, vendor, "two", "bob")
    exchange(bag, session)
    session(vendor, "one", **{field: replacement})
    refused_without_effect(bag, lambda: bag.send("bob", "changed field without join"))
    bag.join(vendor, "ada")
    bag.send("bob", "rejoined")
    assert bag.records()[-1]["from"] == "ada"
    assert bag.door("ada")[field] == replacement
    session(vendor, "one")
    refused_without_effect(bag, lambda: bag.send("bob", "old field no longer owns ada"))


@pytest.mark.parametrize("vendor", ["claude", "codex"])
def test_unrelated_environment_changes_are_not_door_identity(bag, session, monkeypatch, vendor):
    register(bag, session, vendor, "one", "ada")
    register(bag, session, vendor, "two", "bob")
    exchange(bag, session)
    session(vendor, "one")
    monkeypatch.setenv(f"{vendor.upper()}_UNRELATED_TEST_VALUE", "changed")
    bag.send("bob", "defined door fields still match")
    assert bag.records()[-1]["from"] == "ada"


@pytest.mark.parametrize("vendor", ["claude", "codex"])
def test_default_name_is_reserved_for_its_own_vendor(bag, session, vendor):
    fields = session(vendor, "one")
    bag.join(vendor)
    door = bag.door(vendor)
    assert door["peer"] == vendor and door["vendor"] == vendor
    assert all(door[field] == value for field, value in fields.items())


@pytest.mark.parametrize("vendor, name", [("claude", "codex"), ("codex", "claude")])
def test_other_vendor_cannot_take_a_reserved_name(bag, session, vendor, name):
    session(vendor, "one")
    refused_without_effect(bag, lambda: bag.join(vendor, name))


@pytest.mark.parametrize("name", ["", "Ada", "@ada", "0ada", "ada_name", "a" * 17, "adá", "ada bob", "a\n", "../ada"])
def test_invalid_names_are_rejected_before_appending(bag, session, name):
    session("codex", "one")
    refused_without_effect(bag, lambda: bag.join("codex", name))


@pytest.mark.parametrize("name", ["a", "a" * 16, "a0-b", "a-"])
def test_valid_name_boundaries_are_accepted(bag, session, name):
    session("codex", "one")
    bag.join("codex", name)
    assert bag.door(name)["peer"] == name


def test_three_registered_peers_are_experimental_and_share_one_budget(bag, session, capsys):
    register(bag, session, "codex", "one", "ada")
    register(bag, session, "claude", "two", "bob")
    register(bag, session, "codex", "three", "cleo")
    exchange(bag, session, 3)
    capsys.readouterr()
    bag.read(None)
    output = capsys.readouterr().out
    assert "experimental" in output.lower()
    assert all(f"@{name}" in output for name in ("ada", "bob", "cleo"))

    for vendor, identity, recipient in [
        ("codex", "one", "bob"), ("claude", "two", "cleo"), ("codex", "three", "ada"),
    ]:
        session(vendor, identity)
        bag.send(recipient, "one shared letter")
    assert bag.budget() == 0
    assert len(bag.KNOCKED) == 3
    refused_without_effect(bag, lambda: bag.send("bob", "shared budget spent"))


def test_legacy_doors_participate_in_replay_without_rewriting_history(bag, session):
    ada = session("claude", "one")
    bob = session("codex", "two")
    legacy = [
        {"n": 1, "at": "2026-09-08T00:00:00", "kind": "join", "peer": "claude", **ada},
        {"n": 2, "at": "2026-09-08T00:00:01", "kind": "join", "peer": "codex", **bob},
        {"n": 3, "at": "2026-09-08T00:00:02", "kind": "open", "limit": 3},
    ]
    bag.ledger_path().parent.mkdir()
    original = "".join(json.dumps(record) + "\n" for record in legacy)
    bag.ledger_path().write_text(original, encoding="utf-8")
    assert bag.door("claude")["token"] == ada["token"]
    assert bag.door("codex")["thread"] == bob["thread"]
    assert bag.ledger_path().read_text(encoding="utf-8") == original

    session("claude", "one")
    bag.join("claude", "ada")
    session("codex", "two")
    bag.join("codex", "bob")
    refused_without_effect(bag, lambda: bag.door("claude"))
    refused_without_effect(bag, lambda: bag.door("codex"))
    bag.send("@ada", "new names over old doors")
    assert bag.KNOCKED[-1][0] == "claude"
    assert bag.records()[-1]["from"] == "bob"
    assert bag.records()[:3] == legacy
    assert bag.ledger_path().read_text(encoding="utf-8").startswith(original)
