"""Leave wire contracts using private ledgers and fake native transports."""

import asyncio
import fcntl
import importlib.util
import json
from pathlib import Path
import sys

import pytest


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent
MODULES = ("postbag", "postbag_mcp")
SOURCE_LAYOUT = all((SOURCE / f"{module}.py").exists() for module in MODULES)
if SOURCE_LAYOUT and Path(importlib.util.find_spec("postbag_mcp").origin).resolve() != SOURCE / "postbag_mcp.py":
    sys.path.insert(0, str(SOURCE))
    for stale in (*MODULES, "test_mcp"):
        sys.modules.pop(stale, None)

from test_mcp import (  # noqa: E402
    CLAUDE_CONVERSATION, FAKE_TOKEN, SERVER_SCRIPT, STARTUP_THREAD,
    THREAD_A, THREAD_B, checked, checked_read, checked_send, codex_join, letter, meta,
    opened, wire, wire_text,
)

__all__ = ["wire"]


def assert_no_doors(value, *secrets):
    if isinstance(value, dict):
        assert not set(value) & {"thread", "socket", "token", "session_id", "threadId", "sessionId"}
        for child in value.values():
            assert_no_doors(child)
    elif isinstance(value, list):
        for child in value:
            assert_no_doors(child)
    text = json.dumps(value)
    for secret in (THREAD_A, THREAD_B, STARTUP_THREAD, FAKE_TOKEN, *secrets):
        assert secret not in text


def checked_leave(response, *, bag="default", name="ada", vendor="codex", record=2):
    value = checked(response)
    assert value["submission_state"] is None
    assert value["data"] == {"bag": bag, "name": name, "vendor": vendor, "record": record}
    assert_no_doors(value)
    return value


def read_recovery(response, *, bag="default", submission_state=None):
    value = checked(response, ok=False)
    assert value["submission_state"] == submission_state
    assert value["data"] == {"recovery": {"action": "read", "actor": "caller", "bag": bag}}
    assert "postbag_read" in value["message"]
    assert "postbag_join" not in value["message"]
    assert_no_doors(value)
    return value


def test_leave_server_module_uses_source_or_installed_layout():
    origins = {module: Path(importlib.util.find_spec(module).origin).resolve() for module in MODULES}
    if SOURCE_LAYOUT:
        assert origins == {module: SOURCE / f"{module}.py" for module in MODULES}
    else:
        assert origins["postbag"].parent == origins["postbag_mcp"].parent
        assert Path(sys.prefix).resolve() in origins["postbag_mcp"].parents
        assert HERE not in origins["postbag_mcp"].parents
    assert SERVER_SCRIPT.resolve() == origins["postbag_mcp"]


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_leave_catalog_has_only_optional_bag_and_mutation_annotations(wire, mode):
    async def exercise():
        async with wire.session(mode=mode) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            assert set(tools) == {"postbag_join", "postbag_send", "postbag_leave", "postbag_read", "postbag_bags"}
            tool = tools["postbag_leave"]
            assert set(tool.input_schema["properties"]) == {"bag"}
            assert tool.input_schema.get("required", []) == []
            assert tool.input_schema["properties"]["bag"]["default"] == "default"
            assert tool.input_schema["properties"]["bag"]["type"] == "string"
            assert tool.annotations.read_only_hint is False
            assert tool.annotations.destructive_hint is True
            assert tool.annotations.idempotent_hint is False
            assert tool.annotations.open_world_hint is False
            assert tool.output_schema
    asyncio.run(exercise())
    assert not (wire.home / ".postbag").exists()
    assert wire.calls() == []


@pytest.mark.parametrize("bag", ["default", "review"])
def test_join_then_leave_records_only_this_bag_and_redacts_identity(wire, bag):
    other = "other"
    wire.seed(codex_join("ada", THREAD_A), bag=other)
    untouched = wire.path(other).read_bytes()

    async def exercise():
        async with wire.session() as client:
            checked(await client.call_tool("postbag_join", {"name": "ada", "bag": bag}, meta=meta()))
            response = await client.call_tool("postbag_leave", {"bag": bag}, meta=meta())
            checked_leave(response, bag=bag)
            assert THREAD_A not in wire_text(response)
            data = checked_read(await client.call_tool("postbag_read", {"bag": bag}))
            assert_no_doors(data)
            assert data["peers"] == [] and data["letters"] == 0
            assert data["records"][-1] == {
                "n": 2, "at": data["records"][-1]["at"], "kind": "leave", "peer": "ada", "vendor": "codex",
            }
            inventory = checked(await client.call_tool("postbag_bags", {}))["data"]
            assert_no_doors(inventory)
            rows = {row["bag"]: row for row in inventory["bags"]}
            assert rows[bag]["peers"] == [] and rows[bag]["letters"] == 0
            assert rows[other]["peers"] == [{"name": "ada", "vendor": "codex"}]
    asyncio.run(exercise())
    rows = wire.rows(bag)
    assert [row["kind"] for row in rows] == ["join", "leave"]
    assert rows[-1]["thread"] == THREAD_A
    assert set(rows[-1]) == {"n", "at", "kind", "peer", "vendor", "thread"}
    assert wire.path(other).read_bytes() == untouched
    assert wire.calls() == []


def test_leave_history_pagination_keeps_record_cursors_and_letter_counts(wire):
    wire.seed(codex_join("ada", THREAD_A), codex_join("bob", THREAD_B), opened(1),
              letter("earlier"), letter("later", final=True))

    async def exercise():
        async with wire.session() as client:
            checked_leave(await client.call_tool("postbag_leave", {}, meta=meta()), record=6)
            cursor = None
            pages = []
            for numbers, next_cursor in (([5, 6], 5), ([3, 4], 3), ([1, 2], None)):
                args = {"limit": 2, **({"before": cursor} if cursor is not None else {})}
                response = await client.call_tool("postbag_read", args)
                data = checked_read(response)
                assert_no_doors(data)
                assert [row["n"] for row in data["records"]] == numbers
                assert data["next_before"] == next_cursor
                assert data["letters"] == 2
                assert data["peers"] == [{"name": "bob", "vendor": "codex"}]
                for secret in (THREAD_A, THREAD_B, STARTUP_THREAD):
                    assert secret not in wire_text(response)
                pages.append(data["records"])
                cursor = next_cursor
            assert pages[0][0]["letter"] == 2 and pages[0][0]["final"] is True
            assert pages[0][1]["kind"] == "leave" and "letter" not in pages[0][1]
            assert pages[1][0]["kind"] == "open" and pages[1][0]["limit"] == 1
            assert pages[1][1]["letter"] == 1
            inventory = checked(await client.call_tool("postbag_bags", {}))["data"]["bags"]
            assert inventory[0]["letters"] == 2
            assert inventory[0]["peers"] == [{"name": "bob", "vendor": "codex"}]
    asyncio.run(exercise())
    assert len(wire.rows()) == 6 and wire.calls() == []


def test_deliberate_rejoin_restores_sending_and_receiving(wire):
    wire.seed(codex_join("bob", THREAD_B))

    async def exercise():
        async with wire.session() as client:
            checked(await client.call_tool("postbag_join", {"name": "ada"}, meta=meta()))
            checked_leave(await client.call_tool("postbag_leave", {}, meta=meta()), record=3)
            joined = checked(await client.call_tool("postbag_join", {"name": "ada"}, meta=meta()))
            assert joined["data"]["renamed"] is None and joined["data"]["took"] is None
            assert_no_doors(joined)
            for sender, target, text in ((THREAD_A, "bob", "deliberate resumption"),
                                         (THREAD_B, "ada", "response to resumed work")):
                receipt = checked_send(await client.call_tool("postbag_send", {"to": target, "body": text}, meta=meta(sender)))
                assert_no_doors(receipt)
            data = checked_read(await client.call_tool("postbag_read", {}))
            assert_no_doors(data)
            assert data["letters"] == 2
            assert data["peers"] == [{"name": "ada", "vendor": "codex"}, {"name": "bob", "vendor": "codex"}]
            assert [row["kind"] for row in data["records"]] == ["join", "join", "leave", "join", "letter", "letter"]
            assert [row["letter"] for row in data["records"] if row["kind"] == "letter"] == [1, 2]
    asyncio.run(exercise())
    assert len(wire.calls()) == 2
    assert [call[2] for call in wire.calls()] == [THREAD_B, THREAD_A]


@pytest.mark.parametrize("case", ["wrong door", "unheld name", "duplicate leave"])
def test_malformed_leave_replay_refuses_read_and_preserves_partial_inventory(wire, case):
    joined = codex_join("ada", THREAD_A)
    left = {**joined, "kind": "leave"}
    if case == "wrong door":
        records = [joined, {**left, "thread": THREAD_B}]
    elif case == "unheld name":
        records = [joined, {**left, "peer": "bob"}]
    else:
        records = [joined, left, left]
    wire.seed(*records)
    wire.seed(codex_join("bob", THREAD_B), letter("healthy history", "bob", "ada"), bag="healthy")
    before = {bag: wire.path(bag).read_bytes() for bag in ("default", "healthy")}

    async def exercise():
        async with wire.session() as client:
            refused = checked(await client.call_tool("postbag_read", {}), ok=False)
            assert refused["submission_state"] is None
            assert "leaves" in refused["message"]
            assert_no_doors(refused)
            partial = checked(await client.call_tool("postbag_bags", {}), ok=False)
            assert partial["error_code"] == "inventory_incomplete"
            assert partial["submission_state"] is None
            data = partial["data"]
            assert set(data) == {"version", "bags", "total", "offset", "next_offset", "errors", "scope"}
            assert data["version"] == importlib.import_module("postbag").__version__
            assert data["total"] == 2 and data["offset"] == 0 and data["next_offset"] is None
            assert data["errors"]
            rows = {row["bag"]: row for row in data["bags"]}
            assert rows["default"]["peers"] is None and rows["default"]["letters"] is None
            assert rows["healthy"]["peers"] == [{"name": "bob", "vendor": "codex"}]
            assert rows["healthy"]["letters"] == 1
            assert_no_doors(partial)
            assert "healthy history" not in json.dumps(partial)
            healthy = checked_read(await client.call_tool("postbag_read", {"bag": "healthy"}))
            assert healthy["letters"] == 1
            assert_no_doors(healthy)
    asyncio.run(exercise())
    assert {bag: wire.path(bag).read_bytes() for bag in before} == before
    assert wire.calls() == []


def test_departed_sender_and_recipient_refuse_without_rejoin_advice(wire):
    wire.seed(codex_join("ada", THREAD_A), codex_join("bob", THREAD_B))

    async def exercise():
        async with wire.session() as client:
            checked_leave(await client.call_tool("postbag_leave", {}, meta=meta()), record=3)
            before = wire.path().read_bytes()
            left_at = wire.rows()[-1]["at"]
            for sender, target in ((THREAD_A, "bob"), (THREAD_B, "ada")):
                response = await client.call_tool("postbag_send", {"to": target, "body": "queued work"}, meta=meta(sender))
                value = read_recovery(response, submission_state="not_submitted")
                expected = "do not join again unless the human asks you to resume" if sender == THREAD_A else "it left this bag at"
                assert expected in value["message"]
                assert left_at in value["message"]
                assert wire.path().read_bytes() == before
            checked_read(await client.call_tool("postbag_read", {}))
    asyncio.run(exercise())
    assert wire.calls() == []


def test_displaced_sender_hears_that_its_taker_left(wire):
    wire.seed(codex_join("ada", THREAD_A), codex_join("ada", THREAD_B), codex_join("bob", STARTUP_THREAD))
    taken_at = wire.rows()[1]["at"]

    async def exercise():
        async with wire.session() as client:
            checked_leave(await client.call_tool("postbag_leave", {}, meta=meta(THREAD_B)), record=4)
            before = wire.path().read_bytes()
            left_at = wire.rows()[-1]["at"]
            value = checked(await client.call_tool("postbag_send", {"to": "bob", "body": "old queued task"}, meta=meta()), ok=False)
            assert value["error_code"] == "refused" and value["submission_state"] == "not_submitted"
            assert f"your name @ada was taken by the codex door that joined at {taken_at}, which left this bag at {left_at}" in value["message"]
            assert "your name @ada left this bag" not in value["message"]
            assert_no_doors(value)
            assert wire.path().read_bytes() == before
    asyncio.run(exercise())
    assert wire.calls() == []


@pytest.mark.parametrize("case", ["never joined", "already left", "name taken"])
def test_leave_without_current_name_refuses_without_rebinding(wire, case):
    wire.seed(codex_join("bob", THREAD_B))

    async def exercise():
        async with wire.session() as client:
            if case != "never joined":
                checked(await client.call_tool("postbag_join", {"name": "ada"}, meta=meta()))
                if case == "already left":
                    checked_leave(await client.call_tool("postbag_leave", {}, meta=meta()), record=3)
                else:
                    checked(await client.call_tool("postbag_join", {"name": "ada"}, meta=meta(STARTUP_THREAD)))
            before = wire.path().read_bytes()
            value = read_recovery(await client.call_tool("postbag_leave", {}, meta=meta()))
            assert "holds no name" in value["message"]
            assert wire.path().read_bytes() == before
            data = checked_read(await client.call_tool("postbag_read", {}))
            names = {row["name"] for row in data["peers"]}
            assert names == ({"ada", "bob"} if case == "name taken" else {"bob"})
    asyncio.run(exercise())
    assert wire.calls() == []


@pytest.mark.parametrize("bag", ["default", "missing"])
def test_leave_missing_bag_never_creates_files(wire, bag):
    async def exercise():
        async with wire.session() as client:
            value = checked(await client.call_tool("postbag_leave", {"bag": bag}, meta=meta()), ok=False)
            assert value["submission_state"] is None
            assert value["data"] == {"recovery": {"action": "bags", "actor": "caller", "bag": bag}}
            assert "postbag_bags" in value["message"] and "postbag_join" not in value["message"]
    asyncio.run(exercise())
    assert not (wire.home / ".postbag").exists()
    assert wire.calls() == []


def test_leave_rejects_missing_or_invalid_identity_and_unknown_arguments(wire):
    wire.seed(codex_join("ada", THREAD_A))
    before = wire.path().read_bytes()

    async def exercise():
        async with wire.session() as client:
            for identity in (None, {}, {"sessionId": THREAD_A}, {"threadId": "invalid"}):
                value = checked(await client.call_tool("postbag_leave", {}, meta=identity), ok=False)
                assert value["error_code"] == "identity_unavailable"
                assert value["submission_state"] is None
                assert wire.path().read_bytes() == before
            for key, value in (("name", "ada"), ("vendor", "codex"), ("threadId", THREAD_A),
                               ("sessionId", THREAD_A), ("CODEX_THREAD_ID", THREAD_A),
                               ("_meta", meta()), ("extra", True)):
                response = await client.call_tool("postbag_leave", {key: value}, meta=meta())
                outcome = checked(response, ok=False)
                assert outcome["error_code"] == "invalid_input"
                assert outcome["submission_state"] is None
                assert wire.path().read_bytes() == before, key
                assert THREAD_A not in wire_text(response)
            checked_read(await client.call_tool("postbag_read", {}))
    asyncio.run(exercise())
    assert wire.calls() == []


def test_leave_invalid_bag_schema_refuses_without_state(wire):
    async def exercise():
        async with wire.session() as client:
            for bag in ("/tmp/unsafe-ledger", "../other", "Upper", "", None, True, 2):
                response = await client.call_tool("postbag_leave", {"bag": bag}, meta=meta())
                assert response.is_error, bag
            checked(await client.call_tool("postbag_bags", {}))
    asyncio.run(exercise())
    assert not (wire.home / ".postbag").exists()
    assert wire.calls() == []


def test_leave_busy_bag_refuses_then_succeeds_after_unlock(wire):
    wire.seed(codex_join("ada", THREAD_A))
    before = wire.path().read_bytes()

    async def exercise():
        async with wire.session() as client:
            with wire.path().open("r") as held:
                fcntl.flock(held, fcntl.LOCK_EX)
                value = read_recovery(await client.call_tool("postbag_leave", {}, meta=meta()))
                assert value["error_code"] == "ledger_busy"
                assert wire.path().read_bytes() == before
            checked_leave(await client.call_tool("postbag_leave", {}, meta=meta()))
    asyncio.run(exercise())
    assert wire.calls() == []


def test_shared_claude_inbox_leave_withdraws_parent_and_sibling(wire, tmp_path):
    inbox = str(tmp_path / "unused-inbox.sock")
    common = {"CLAUDECODE": "1", "CLAUDE_CODE_MESSAGING_SOCKET": inbox,
              "CLAUDE_CODE_MESSAGING_TOKEN": FAKE_TOKEN}
    parent = {**common, "CLAUDE_CODE_SESSION_ID": CLAUDE_CONVERSATION}
    sibling = {**common, "CLAUDE_CODE_SESSION_ID": THREAD_B}
    wire.seed(codex_join("bob", THREAD_B))

    async def exercise():
        async with wire.session(extra=parent) as first, wire.session(extra=sibling) as second:
            checked(await first.call_tool("postbag_join", {"name": "reader"}))
            response = await second.call_tool("postbag_leave", {})
            checked_leave(response, name="reader", vendor="claude", record=3)
            before = wire.path().read_bytes()
            for client in (first, second):
                value = read_recovery(await client.call_tool("postbag_send", {"to": "bob", "body": "old queued work"}),
                                      submission_state="not_submitted")
                assert "left" in value["message"]
                read_recovery(await client.call_tool("postbag_leave", {}))
                assert wire.path().read_bytes() == before
            data = checked_read(await first.call_tool("postbag_read", {}))
            assert_no_doors(data, inbox, CLAUDE_CONVERSATION)
            assert data["peers"] == [{"name": "bob", "vendor": "codex"}]
            public = json.dumps(data) + wire_text(response)
            for secret in (inbox, FAKE_TOKEN, CLAUDE_CONVERSATION, THREAD_B):
                assert secret not in public
    asyncio.run(exercise())
    leave = wire.rows()[-1]
    assert leave["kind"] == "leave" and leave["socket"] == inbox and leave["token"] == FAKE_TOKEN
    assert "session_id" not in leave
    assert wire.calls() == []
