"""Adversarial wire checks: races, hostile inputs, boundaries, paging and shutdown.

Complements test_mcp.py and test_mcp_review.py without repeating them. The
fixtures come from test_mcp: isolated HOME, fake native executable, real SDK
stdio client. Nothing here touches ~/.postbag.
"""

import asyncio
import errno
import importlib.util
import json
from pathlib import Path
import sys
import time

import pytest

HERE = Path(__file__).resolve().parent
if (HERE / "postbag.py").exists():
    # Source layout: test the checkout beside this file, not some other import of the same name.
    spec = importlib.util.find_spec("postbag_mcp")
    if spec is None or Path(spec.origin).resolve() != HERE / "postbag_mcp.py":
        sys.path.insert(0, str(HERE))
        for stale in ("postbag_mcp", "postbag", "test_mcp"):
            sys.modules.pop(stale, None)
# Installed layout (only test_mcp*.py copied elsewhere): use the installed package as found.

from test_mcp import (  # noqa: E402
    FAKE_TOKEN, THREAD_A, THREAD_B, checked, checked_read, checked_send, codex_join, letter, meta, wire,
)
import postbag  # noqa: E402
import postbag_mcp  # noqa: E402

__all__ = ["wire"]

BOUNDARY = 65536


def peers(wire):
    return wire.seed(codex_join("ada", THREAD_A), codex_join("bob", THREAD_B))


def letters(rows):
    return [row for row in rows if row["kind"] == "letter"]


# 1. two identities race for the ledger ---------------------------------------

@pytest.mark.parametrize("attempt", range(2))
def test_two_identities_racing_preserve_sender_and_unique_letter_numbers(wire, attempt):
    peers(wire)
    outcomes = []

    async def exercise():
        async with wire.session(extra={"POSTBAG_TEST_SLEEP": "0.3"}) as client:
            results = await asyncio.gather(
                client.call_tool("postbag_send", {"to": "bob", "body": "from ada"}, meta=meta(THREAD_A)),
                client.call_tool("postbag_send", {"to": "ada", "body": "from bob"}, meta=meta(THREAD_B)),
            )
            for result in results:
                value = checked_send(result) if not result.is_error else checked(result, ok=False)
                if not value["ok"]:
                    assert value["submission_state"] == "not_submitted"
                    assert value["error_code"] == "ledger_busy"
                outcomes.append(value)
    asyncio.run(exercise())
    accepted = [value for value in outcomes if value["ok"]]
    assert 1 <= len(accepted) <= 2
    recorded = letters(wire.rows())
    assert len(wire.calls()) == len(recorded) == len(accepted)
    expected = [("ada", "bob", "from ada"), ("bob", "ada", "from bob")]
    assert sorted((row["from"], row["to"], row["body"]) for row in recorded) == sorted(
        entry for entry, value in zip(expected, outcomes) if value["ok"])
    assert sorted(value["data"]["letter"] for value in accepted) == list(range(1, len(accepted) + 1))
    assert [row["n"] for row in recorded] == list(range(3, len(accepted) + 3))


# 2. hostile recipient and thread values -----------------------------------------------

HOSTILE_TO = ["@BOB", "Bob", "../bob", "bob/../ada", "@@bob", " bob", "bob\n", "@", "",
              "bob\0", "@bob ", "/bob", "@../bob", "b" * 17, "@" + "b" * 17, "bob@", "b@ob", "ada bob"]


def test_hostile_recipient_values_are_refused_before_transport(wire):
    peers(wire)
    before = wire.path().read_bytes()

    async def exercise():
        async with wire.session() as client:
            for to in HOSTILE_TO:
                result = await client.call_tool("postbag_send", {"to": to, "body": "probe"}, meta=meta())
                assert result.is_error, (to, result)
            checked(await client.call_tool("postbag_send", {"to": "bob", "body": "still serving"}, meta=meta()))
    asyncio.run(exercise())
    assert wire.path().read_bytes() != before
    assert [row["body"] for row in letters(wire.rows())] == ["still serving"]
    assert len(wire.calls()) == 1


NOT_A_THREAD = ["{aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa}", "urn:uuid:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                " aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa\n",
                "aaaaaaaaaaaa4aaa8aaaaaaaaaaaaaaa", "gggggggg-gggg-4ggg-8ggg-gggggggggggg",
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa; rm -rf", "",
                "\uff41\uff41\uff41\uff41\uff41\uff41\uff41\uff41-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                {"nested": THREAD_A}, 1.5, True]


def test_non_uuid_thread_ids_are_refused_and_uppercase_is_normalised(wire):
    async def exercise():
        async with wire.session() as client:
            for thread in NOT_A_THREAD:
                result = checked(await client.call_tool("postbag_join", {"name": "ada"},
                                                        meta={"threadId": thread}), ok=False)
                assert result["error_code"] == "identity_unavailable", thread
            assert wire.rows() == []
            checked(await client.call_tool("postbag_join", {"name": "ada"}, meta={"threadId": THREAD_A.upper()}))
    asyncio.run(exercise())
    assert [row["thread"] for row in wire.rows()] == [THREAD_A]
    assert wire.calls() == []


# 3. the byte boundary for every code point width ---------------------------------------

def test_body_limit_is_exact_for_two_three_and_four_byte_code_points(wire):
    fits = ["\u00e9" * (BOUNDARY // 2), "\u20ac" * (BOUNDARY // 3) + "a", "\U0001f30d" * (BOUNDARY // 4)]
    exceeds = [body + "a" for body in fits]
    assert all(len(body.encode()) == BOUNDARY for body in fits)
    assert all(len(body.encode()) == BOUNDARY + 1 for body in exceeds)
    peers(wire)

    async def exercise():
        async with wire.session() as client:
            for body in exceeds:
                over = checked(await client.call_tool("postbag_send", {"to": "bob", "body": body}, meta=meta()), ok=False)
                assert over["error_code"] == "invalid_input" and over["submission_state"] == "not_submitted"
            assert wire.calls() == []
            for body in fits:
                checked(await client.call_tool("postbag_send", {"to": "bob", "body": body}, meta=meta()))
    asyncio.run(exercise())
    assert [len(row["body"].encode()) for row in letters(wire.rows())] == [BOUNDARY] * 3
    assert [body in call[-1] for body, call in zip(fits, wire.calls())] == [True] * 3


# 4. pagination edges and a large page ----------------------------------------------------

def test_read_pagination_edges(wire):
    rows = wire.seed(codex_join("ada", THREAD_A), letter("one"), letter("two"), letter("three"))

    async def exercise():
        async with wire.session() as client:
            async def page(**arguments):
                return checked_read(await client.call_tool("postbag_read", arguments))
            first = await page(before=1)
            assert first["records"] == [] and first["next_before"] is None
            assert first["letters"] == 3, "state describes the whole bag, not the page"
            assert [row["n"] for row in (await page(before=10 ** 12))["records"]] == [1, 2, 3, 4]
            edge = await page(before=len(rows))
            assert [row["n"] for row in edge["records"]] == [1, 2, 3] and edge["next_before"] is None
            single = await page(limit=1)
            assert [row["n"] for row in single["records"]] == [4] and single["next_before"] == 4
            chained = await page(limit=1, before=single["next_before"])
            assert [row["n"] for row in chained["records"]] == [3] and chained["next_before"] == 3
            last = await page(limit=1, before=2)
            assert [row["n"] for row in last["records"]] == [1] and last["next_before"] is None
            wire.path().unlink()
            missing = checked(await client.call_tool("postbag_read", {"limit": 100, "before": 1}), ok=False)
            assert missing["submission_state"] is None
            assert not wire.path().exists()
    asyncio.run(exercise())
    assert wire.calls() == []


def test_read_limit_100_over_three_thousand_records(wire):
    body = "\u03ba\u03b1\u03bb\u03b7\u03bc\u03ad\u03c1\u03b1 " * 40
    wire.seed(codex_join("ada", THREAD_A), *(letter(f"{body}{index}") for index in range(3000)))

    async def exercise():
        async with wire.session() as client:
            started = time.monotonic()
            page = checked_read(await client.call_tool("postbag_read", {"limit": 100}))
            assert time.monotonic() - started < 5
            assert [row["n"] for row in page["records"]] == list(range(2902, 3002))
            assert page["next_before"] == 2902 and page["letters"] == 3000
            assert [row["letter"] for row in page["records"]] == list(range(2901, 3001))
            previous = checked_read(await client.call_tool("postbag_read", {"limit": 100, "before": 2902}))
            assert [row["n"] for row in previous["records"]] == list(range(2802, 2902))
            assert previous["records"][0]["body"].startswith(body)
    asyncio.run(exercise())


# 5. a bag that is a valid name but does not exist ------------------------------------------

@pytest.mark.parametrize("bag", ["default", "ghost-bag"])
@pytest.mark.parametrize("tool,arguments", [
    ("postbag_send", {"to": "bob", "body": "hello"}),
    ("postbag_read", {}),
])
def test_nonexistent_bag_is_refused_without_creating_directories(wire, bag, tool, arguments):
    async def exercise():
        async with wire.session() as client:
            result = checked(await client.call_tool(tool, {**arguments, "bag": bag}, meta=meta()), ok=False)
            assert result["error_code"] == "refused"
            assert result["submission_state"] == ("not_submitted" if tool == "postbag_send" else None)
            action = "join" if tool == "postbag_send" else "bags"
            recovery = {"action": action, "actor": "caller", "bag": bag}
            if tool == "postbag_send":
                recovery.update(vendor="codex", name=None)
            assert result["data"]["recovery"] == recovery
            assert f"postbag_{action}" in result["message"]
            assert result["message"].endswith("; stop and ask the human")
    asyncio.run(exercise())
    assert not (wire.home / ".postbag").exists()
    assert wire.calls() == []


# 6. the environment a Codex caller's transport child receives ------------------------------

def test_codex_transport_child_sees_only_its_own_identity(wire, tmp_path):
    peers(wire)
    dump = tmp_path / "codex-env.json"
    spy = tmp_path / "spy-codex"
    spy.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "with open(os.environ['POSTBAG_TEST_CAPTURE'], 'a') as output:\n"
        "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        f"json.dump(dict(os.environ), open({str(dump)!r}, 'w'))\n",
        encoding="utf-8",
    )
    spy.chmod(0o700)
    # A token without a socket is not a Claude host, so threadId still selects Codex.
    hostile = {"POSTBAG_CODEX": str(spy), "POSTBAG_LEDGER": str(tmp_path / "evil.jsonl"),
               "CLAUDE_CODE_MESSAGING_TOKEN": FAKE_TOKEN, "CLAUDECODE": "1"}

    async def exercise():
        async with wire.session(extra=hostile) as client:
            checked(await client.call_tool("postbag_send", {"to": "bob", "body": "env probe"}, meta=meta()))
    asyncio.run(exercise())
    env = json.loads(dump.read_text())
    assert postbag.HIDDEN_FROM_CHILD.isdisjoint(env), sorted(postbag.HIDDEN_FROM_CHILD & set(env))
    assert FAKE_TOKEN not in json.dumps(env) and THREAD_A not in json.dumps(env)
    assert env["POSTBAG_CODEX"] == str(spy) and env["HOME"] == str(wire.home)
    assert wire.calls()[0][2] == THREAD_B, "the thread travels as an argument, never as environment"
    assert not (tmp_path / "evil.jsonl").exists()
    assert [row["body"] for row in letters(wire.rows())] == ["env probe"]


# 7. recording after the knock -----------------------------------------------------------------

def test_client_closed_mid_knock_still_records_the_letter(wire):
    """The SDK's 2 s grace expires and it signals the server group; the worker outlives it."""
    peers(wire)

    async def exercise():
        async with wire.session(extra={"POSTBAG_TEST_SLEEP": "2.5"}) as client:
            pending = asyncio.create_task(client.call_tool(
                "postbag_send", {"to": "bob", "body": "abandoned by its client"}, meta=meta()))
            deadline = asyncio.get_running_loop().time() + 10
            while not wire.calls():
                assert asyncio.get_running_loop().time() < deadline
                await asyncio.sleep(0.02)
        pending.cancel()
        with pytest.raises(BaseException):
            await pending
    asyncio.run(exercise())
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and not letters(wire.rows()):
        time.sleep(0.1)
    assert len(wire.calls()) == 1
    assert [row["body"] for row in letters(wire.rows())] == ["abandoned by its client"]


def test_fsync_failure_after_knock_reports_unconfirmed_recording(tmp_path, monkeypatch):
    """The record may be on disk without confirmed durability; the caller must not be told it is absent."""
    home = tmp_path / "home"
    ledger = home / ".postbag" / "ledger.jsonl"
    ledger.parent.mkdir(parents=True)
    rows = [dict(n=index, at="2026-09-30T10:00:00+00:00", **row) for index, row in enumerate(
        (codex_join("ada", THREAD_A), codex_join("bob", THREAD_B)), 1)]
    ledger.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    ledger.chmod(0o600)
    monkeypatch.setenv("HOME", str(home))
    for variable in postbag_mcp.SESSION_VARS | {"POSTBAG_LEDGER", "POSTBAG_CODEX"}:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("CODEX_THREAD_ID", THREAD_A)
    monkeypatch.setenv("CODEX_SESSION_ID", THREAD_A)
    knocks = []
    monkeypatch.setitem(postbag.KNOCK, "codex", lambda door, text: knocks.append(door["thread"]))

    def failing_fsync(fd):
        raise OSError(errno.EIO, "simulated I/O error")
    monkeypatch.setattr(postbag.os, "fsync", failing_fsync)

    result = postbag_mcp.worker({"operation": "send", "vendor": "codex",
                                 "arguments": {"to": "bob", "body": "durability unknown", "bag": "default"}})
    assert result["ok"] is False
    assert result["error_code"] == "recording_failed"
    assert result["submission_state"] == "submitted"
    assert "recording could not be confirmed" in result["message"]
    assert "not recorded" not in result["message"]
    assert knocks == [THREAD_B]
    on_disk = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert [row["body"] for row in letters(on_disk)] == ["durability unknown"]
    assert on_disk[:-1] == rows and len(on_disk) == len(rows) + 1
    assert postbag.Snapshot(on_disk).letters == 1
