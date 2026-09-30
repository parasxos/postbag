"""Real MCP SDK subprocess checks with private ledgers and fake native doors."""

import asyncio
from contextlib import asynccontextmanager
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import select
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

import pytest

pytest.importorskip("mcp", reason="MCP wire checks require the optional mcp extra")
try:
    from mcp import Client, StdioServerParameters, stdio_client
except ImportError:
    pytest.skip("MCP wire checks require mcp 2.x", allow_module_level=True)


ROOT = Path(__file__).resolve().parent
SERVER_SCRIPT = Path(importlib.util.find_spec("postbag_mcp").origin)
THREAD_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
THREAD_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
STARTUP_THREAD = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
TRANSIENT_SESSION = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
FAKE_TOKEN = "postbag-test-private-claude-token"
CLAUDE_CONVERSATION = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"


def meta(thread=THREAD_A):
    return {"threadId": thread, "sessionId": TRANSIENT_SESSION}


def checked(result, *, ok=True):
    """Assert the public result contract, not SDK internals or prose."""
    value = result.structured_content
    assert isinstance(value, dict), result
    assert set(value) == {"ok", "error_code", "submission_state", "message", "data"}
    assert value["ok"] is ok
    assert result.is_error is (not ok)
    assert isinstance(value["message"], str)
    assert isinstance(value["data"], dict)
    assert (value["error_code"] is None) if ok else isinstance(value["error_code"], str)
    assert result.content and all(item.type == "text" for item in result.content)
    return value


def wire_text(result):
    return json.dumps(result.model_dump(mode="json"))


@pytest.fixture
def wire(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    capture = tmp_path / "native-calls.jsonl"
    fake_codex = tmp_path / "fake-codex"
    fake_codex.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys, time\n"
        "with open(os.environ['POSTBAG_TEST_CAPTURE'], 'a') as output:\n"
        "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "time.sleep(float(os.environ.get('POSTBAG_TEST_SLEEP', '0.04')))\n"
        "print('private native output', sys.argv[3], file=sys.stderr)\n"
        "print('private native output', sys.argv[3])\n"
        "raise SystemExit(int(os.environ.get('POSTBAG_TEST_EXIT', '0')))\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o700)
    environment = {
        "HOME": str(home),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "POSTBAG_CODEX": str(fake_codex),
        "POSTBAG_TEST_CAPTURE": str(capture),
        # A shared host may launch the server from some unrelated session.
        "CODEX_SESSION_ID": STARTUP_THREAD,
        "CODEX_THREAD_ID": STARTUP_THREAD,
    }
    logs = []

    @asynccontextmanager
    async def session(*, extra=None, mode="auto", pinned=False):
        log = tmp_path / f"server-{len(logs)}.stderr"
        logs.append(log)
        server = StdioServerParameters(
            command=sys.executable,
            args=[str(SERVER_SCRIPT)] if pinned else ["-m", "postbag_mcp"],
            env={**environment, **(extra or {})},
            cwd=tmp_path,
        )
        with log.open("w", encoding="utf-8") as errors:
            async with Client(stdio_client(server, errlog=errors), mode=mode,
                              read_timeout_seconds=15) as client:
                yield client

    def path(bag="default"):
        return home / ".postbag" / ("ledger.jsonl" if bag == "default" else f"bags/{bag}.jsonl")

    def seed(*records, bag="default"):
        target = path(bag)
        target.parent.mkdir(parents=True, exist_ok=True)
        rows = [dict(n=index, at="2026-09-30T10:00:00+00:00", **row)
                for index, row in enumerate(records, 1)]
        target.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        target.chmod(0o600)
        return rows

    def rows(bag="default"):
        target = path(bag)
        return [json.loads(line) for line in target.read_text().splitlines()] if target.exists() else []

    def calls():
        return [json.loads(line) for line in capture.read_text().splitlines()] if capture.exists() else []

    state = SimpleNamespace(home=home, session=session, path=path, seed=seed, rows=rows,
                            calls=calls, logs=logs, environment=environment)
    yield state
    for log in logs:
        text = log.read_text()
        assert FAKE_TOKEN not in text
        assert "private native output" not in text


def codex_join(name, thread):
    return {"kind": "join", "peer": name, "vendor": "codex", "thread": thread}


def opened(limit):
    return {"kind": "open", "limit": limit}


def letter(body, sender="ada", recipient="bob"):
    return {"kind": "letter", "from": sender, "to": recipient, "body": body}


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_sdk_stdio_catalog_and_readonly_empty_inventory(wire, mode):
    async def exercise():
        async with wire.session(mode=mode) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            assert set(tools) == {"postbag_join", "postbag_send", "postbag_read", "postbag_bags"}
            assert set(tools["postbag_join"].input_schema["properties"]) == {"name", "bag"}
            assert set(tools["postbag_send"].input_schema["properties"]) == {"to", "body", "bag"}
            assert set(tools["postbag_read"].input_schema["properties"]) == {"bag", "limit", "before"}
            assert set(tools["postbag_bags"].input_schema["properties"]) == {"limit", "offset"}
            assert all(tool.output_schema for tool in tools.values())
            assert tools["postbag_join"].annotations.destructive_hint is True
            assert tools["postbag_read"].annotations.read_only_hint is True
            assert tools["postbag_bags"].annotations.read_only_hint is True
            result = checked(await client.call_tool("postbag_bags", {}))["data"]
            assert result["bags"] == [] and result["total"] == 0
            assert result["next_offset"] is None
            checked(await client.call_tool("postbag_read", {}))
            absent = await client.call_tool("postbag_open", {"limit": 999})
            assert absent.is_error
    asyncio.run(exercise())
    assert not (wire.home / ".postbag").exists()
    assert wire.calls() == []


def test_request_metadata_selects_each_sender_and_ignores_startup_identity(wire):
    wire.seed(opened(2))

    async def exercise():
        async with wire.session() as client:
            missing = checked(await client.call_tool("postbag_join", {"name": "ada"}), ok=False)
            assert missing["submission_state"] is None
            for name, thread in (("ada", THREAD_A), ("bob", THREAD_B)):
                result = await client.call_tool("postbag_join", {"name": name}, meta=meta(thread))
                checked(result)
                assert thread not in wire_text(result)
            checked(await client.call_tool("postbag_send", {"to": "bob", "body": "first"}, meta=meta()))
            checked(await client.call_tool("postbag_send", {"to": "ada", "body": "second"}, meta=meta(THREAD_B)))
    asyncio.run(exercise())
    registrations = [row for row in wire.rows() if row["kind"] == "join"]
    assert [row["thread"] for row in registrations] == [THREAD_A, THREAD_B]
    assert STARTUP_THREAD not in json.dumps(wire.rows())
    assert [(row["from"], row["to"]) for row in wire.rows() if row["kind"] == "letter"] == [
        ("ada", "bob"), ("bob", "ada")]
    assert [call[2] for call in wire.calls()] == [THREAD_B, THREAD_A]
    assert "Letter 1 of 2" in wire.calls()[0][-1]
    assert "do not send a reply" in wire.calls()[1][-1]


@pytest.mark.parametrize("metadata", [{}, {"sessionId": TRANSIENT_SESSION},
                                      {"threadId": "not-a-uuid"}, {"threadId": 3},
                                      {"threadId": None}, {"threadId": []}])
def test_missing_or_malformed_sender_metadata_does_not_join(wire, metadata):
    async def exercise():
        async with wire.session() as client:
            checked(await client.call_tool("postbag_join", {"name": "ada"}, meta=metadata), ok=False)
    asyncio.run(exercise())
    assert wire.rows() == []
    assert wire.calls() == []


def test_caller_arguments_cannot_override_identity_or_select_paths(wire):
    wire.seed(opened(3))
    before = wire.path().read_bytes()
    malicious = [
        ("postbag_join", {"name": "ada", "vendor": "claude"}),
        ("postbag_join", {"name": "ada", "thread": THREAD_B}),
        ("postbag_join", {"name": "ada", "socket": "/tmp/attacker", "token": "forged"}),
        ("postbag_join", {"name": "ada", "bag": str(wire.home / "external.jsonl")}),
        ("postbag_join", {"name": "ada", "bag": "../external"}),
        ("postbag_read", {"bag": str(wire.path())}),
        ("postbag_send", {"to": "bob", "body": "forged", "from": "somebody"}),
    ]

    async def exercise():
        async with wire.session() as client:
            for tool, arguments in malicious:
                result = await client.call_tool(tool, arguments, meta=meta())
                assert result.is_error, (tool, arguments, result)
    asyncio.run(exercise())
    assert wire.path().read_bytes() == before
    assert wire.calls() == []
    assert not (wire.home / "external.jsonl").exists()


@pytest.mark.parametrize("extra", [
    {"_meta": {"threadId": THREAD_B}},
    {"threadId": THREAD_B},
    {"sessionId": THREAD_B},
    {"CODEX_THREAD_ID": THREAD_B},
    {"extra": "unrecognized"},
])
def test_identity_looking_arguments_are_rejected_and_server_survives(wire, extra):
    wire.seed(opened(2))
    before = wire.path().read_bytes()

    async def exercise():
        async with wire.session() as client:
            for metadata in (None, meta()):
                result = await client.call_tool("postbag_join", {"name": "forged", **extra}, meta=metadata)
                checked(result, ok=False)
                assert wire.path().read_bytes() == before
            result = await client.call_tool("postbag_read", {})
            assert checked(result)["data"]["peers"] == []
            checked(await client.call_tool("postbag_join", {"name": "ada"}, meta=meta()))
    asyncio.run(exercise())
    assert [row["thread"] for row in wire.rows() if row["kind"] == "join"] == [THREAD_A]
    assert wire.calls() == []


def test_read_pagination_and_inventory_redact_endpoint_fields(wire):
    secret_socket = "/tmp/postbag-mcp-private-socket"
    wire.seed(opened(4), codex_join("ada", THREAD_A),
              {"kind": "join", "peer": "bob", "vendor": "claude", "socket": secret_socket,
               "token": FAKE_TOKEN, "session_id": CLAUDE_CONVERSATION},
              letter("older body"), letter("newer body"))
    before = wire.path().read_bytes()

    async def exercise():
        async with wire.session() as client:
            first = await client.call_tool("postbag_read", {"limit": 2})
            data = checked(first)["data"]
            assert [row["n"] for row in data["records"]] == [4, 5]
            assert data["next_before"] == 4
            assert [row["letter"] for row in data["records"]] == [1, 2]
            assert data["remaining"] == 2
            assert data["peers"] == [{"name": "ada", "vendor": "codex"}, {"name": "bob", "vendor": "claude"}]
            second = await client.call_tool("postbag_read", {"limit": 2, "before": 4})
            data = checked(second)["data"]
            assert [row["n"] for row in data["records"]] == [2, 3]
            assert data["next_before"] == 2
            third = await client.call_tool("postbag_read", {"limit": 2, "before": 2})
            data = checked(third)["data"]
            assert [row["n"] for row in data["records"]] == [1]
            assert data["next_before"] is None
            inventory = await client.call_tool("postbag_bags", {})
            inventory_data = checked(inventory)["data"]
            assert inventory_data["total"] == 1
            for result in (first, second, third, inventory):
                output = wire_text(result)
                for secret in (THREAD_A, FAKE_TOKEN, secret_socket, CLAUDE_CONVERSATION):
                    assert secret not in output
            assert "older body" not in wire_text(inventory)
            assert "newer body" not in wire_text(inventory)
    asyncio.run(exercise())
    assert wire.path().read_bytes() == before
    assert wire.calls() == []


@pytest.mark.parametrize("tool,arguments", [
    ("postbag_read", {"limit": 0}), ("postbag_read", {"limit": 101}),
    ("postbag_read", {"limit": True}), ("postbag_read", {"limit": "2"}),
    ("postbag_read", {"before": 0}), ("postbag_bags", {"limit": 0}),
    ("postbag_bags", {"limit": 101}), ("postbag_bags", {"offset": -1}),
    ("postbag_bags", {"offset": True}), ("postbag_join", {"name": 123}),
    ("postbag_send", {"to": "bob"}),
])
def test_invalid_tool_inputs_refuse_without_state(wire, tool, arguments):
    async def exercise():
        async with wire.session() as client:
            assert (await client.call_tool(tool, arguments, meta=meta())).is_error
    asyncio.run(exercise())
    assert wire.rows() == []
    assert wire.calls() == []


def test_budget_exhaustion_and_invalid_text_never_reach_transport(wire):
    wire.seed(codex_join("ada", THREAD_A), codex_join("bob", THREAD_B), opened(1))

    async def exercise():
        async with wire.session() as client:
            for body in ("  ", "a\0b"):
                checked(await client.call_tool("postbag_send", {"to": "bob", "body": body}, meta=meta()), ok=False)
            assert wire.calls() == []
            accepted = checked(await client.call_tool("postbag_send", {"to": "bob", "body": "one"}, meta=meta()))
            assert accepted["submission_state"] == "submitted"
            before = wire.path().read_bytes()
            refused = checked(await client.call_tool("postbag_send", {"to": "bob", "body": "two"}, meta=meta()), ok=False)
            assert refused["submission_state"] != "submitted"
            assert wire.path().read_bytes() == before
    asyncio.run(exercise())
    assert len(wire.calls()) == 1
    assert len([row for row in wire.rows() if row["kind"] == "letter"]) == 1


def test_missing_named_bag_and_unopened_exchange_cannot_create_budget(wire):
    wire.seed(codex_join("ada", THREAD_A), codex_join("bob", THREAD_B))
    before = wire.path().read_bytes()

    async def exercise():
        async with wire.session() as client:
            checked(await client.call_tool("postbag_join", {"name": "ada", "bag": "missing"}, meta=meta()), ok=False)
            checked(await client.call_tool("postbag_read", {"bag": "missing"}), ok=False)
            checked(await client.call_tool("postbag_send", {"to": "bob", "body": "no budget"}, meta=meta()), ok=False)
    asyncio.run(exercise())
    assert wire.path().read_bytes() == before
    assert not wire.path("missing").exists()
    assert wire.calls() == []


def test_payload_limit_is_utf8_bytes_and_rejection_preserves_budget(wire):
    wire.seed(codex_join("ada", THREAD_A), codex_join("bob", THREAD_B), opened(1))
    before = wire.path().read_bytes()

    async def exercise():
        async with wire.session() as client:
            # Each case fits the schema's character bound but exceeds the byte bound.
            for body in ("\u00e9" * 32769, "\U0001f30d" * 16385):
                result = await client.call_tool("postbag_send", {"to": "bob", "body": body}, meta=meta())
                checked(result, ok=False)
            assert wire.calls() == [] and wire.path().read_bytes() == before
            checked(await client.call_tool("postbag_send", {"to": "bob", "body": "x" * 65536}, meta=meta()))
    asyncio.run(exercise())
    assert len(wire.calls()) == 1


def test_cancelled_call_finishes_recording_inflight_submission(wire):
    wire.seed(codex_join("ada", THREAD_A), codex_join("bob", THREAD_B), opened(1))

    async def exercise():
        async with wire.session(extra={"POSTBAG_TEST_SLEEP": "0.6"}) as client:
            call = asyncio.create_task(client.call_tool(
                "postbag_send", {"to": "bob", "body": "cancel after submission"}, meta=meta()))
            deadline = asyncio.get_running_loop().time() + 10
            while not wire.calls():
                assert asyncio.get_running_loop().time() < deadline, "fake transport never received the letter"
                await asyncio.sleep(0.02)
            call.cancel()
            with pytest.raises(asyncio.CancelledError):
                await call
            # Closing the client asks the server to shut down. Its pending worker
            # must finish and be reaped, rather than terminating between knock/append.
    asyncio.run(exercise())
    assert len(wire.calls()) == 1
    assert [row["body"] for row in wire.rows() if row["kind"] == "letter"] == ["cancel after submission"]


@pytest.mark.parametrize("delay", [1.0, 2.5])
def test_stdio_eof_waits_for_submitted_letter_to_be_recorded(wire, tmp_path, delay):
    """Test the server's graceful shutdown without an SDK client's kill timer."""
    wire.seed(codex_join("ada", THREAD_A), codex_join("bob", THREAD_B), opened(1))
    log = tmp_path / "raw-eof.stderr"
    with log.open("w", encoding="utf-8") as errors:
        process = subprocess.Popen(
            [sys.executable, str(SERVER_SCRIPT)],
            cwd=tmp_path, env={**wire.environment, "POSTBAG_TEST_SLEEP": str(delay)},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
            text=True, start_new_session=True,
        )
        try:
            initialize = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-11-25", "capabilities": {},
                "clientInfo": {"name": "postbag-private-wire-test", "version": "1"}}}
            process.stdin.write(json.dumps(initialize) + "\n")
            process.stdin.flush()
            assert select.select([process.stdout], [], [], 10)[0], "initialize did not return"
            response = json.loads(process.stdout.readline())
            assert response["id"] == 1 and "result" in response
            process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
            call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "postbag_send", "arguments": {"to": "bob", "body": "EOF after submission"},
                "_meta": meta()}}
            process.stdin.write(json.dumps(call) + "\n")
            process.stdin.flush()
            deadline = time.monotonic() + 10
            while not wire.calls():
                assert time.monotonic() < deadline, "fake native side effect did not occur"
                assert process.poll() is None, log.read_text()
                time.sleep(0.01)
            process.stdin.close()
            process.stdin = None
            remainder, _ = process.communicate(timeout=10)
            assert process.returncode == 0, log.read_text()
            # A response may already have been written before shutdown. Any output
            # still has to be protocol JSON, never CLI prose or vendor output.
            for line in remainder.splitlines():
                assert json.loads(line)["jsonrpc"] == "2.0"
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
    assert len(wire.calls()) == 1
    assert [row["body"] for row in wire.rows() if row["kind"] == "letter"] == ["EOF after submission"]
    assert "private native output" not in log.read_text()
    assert FAKE_TOKEN not in log.read_text()


def test_worker_never_imports_modules_from_the_host_project(wire, tmp_path):
    marker = tmp_path / "host-code-executed"
    for filename in ("postbag.py", "postbag_mcp.py"):
        (tmp_path / filename).write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text({filename!r})\n"
            "raise SystemExit(91)\n",
            encoding="utf-8",
        )
    results = []

    async def exercise():
        # Pin the server entry point so this checks worker resolution rather than
        # intentionally asking `python -m` to run the fixture's hostile server.
        async with wire.session(pinned=True) as client:
            results.append(await client.call_tool("postbag_join", {"name": "ada"}, meta=meta()))
            results.append(await client.call_tool("postbag_read", {}))
    asyncio.run(exercise())
    assert not marker.exists(), "worker imported the host project's Python module"
    for result in results:
        checked(result)
    assert wire.rows()[0]["thread"] == THREAD_A


def test_concurrent_last_slot_has_one_submission_and_no_retry(wire):
    wire.seed(codex_join("ada", THREAD_A), codex_join("bob", THREAD_B), opened(1))

    async def exercise():
        async with wire.session() as client:
            results = await asyncio.gather(*(
                client.call_tool("postbag_send", {"to": "bob", "body": f"contender {index}"}, meta=meta())
                for index in range(8)))
            assert sum(not result.is_error for result in results) == 1
            for result in results:
                checked(result, ok=not result.is_error)
    asyncio.run(exercise())
    assert len(wire.calls()) == 1
    assert len([row for row in wire.rows() if row["kind"] == "letter"]) == 1


def test_concurrent_calls_keep_bags_and_callers_separate(wire):
    for bag in ("alpha", "beta"):
        wire.seed(codex_join("ada", THREAD_A), codex_join("bob", THREAD_B), opened(2), bag=bag)

    async def exercise():
        async with wire.session() as client:
            results = await asyncio.gather(
                client.call_tool("postbag_send", {"to": "bob", "body": "only alpha", "bag": "alpha"}, meta=meta()),
                client.call_tool("postbag_send", {"to": "ada", "body": "only beta", "bag": "beta"}, meta=meta(THREAD_B)),
                client.call_tool("postbag_bags", {}),
            )
            for result in results[:2]:
                checked(result)
            # A simultaneous inventory may report a busy bag, but may not mix identities.
            assert isinstance(results[2].structured_content, dict)
    asyncio.run(exercise())
    alpha = [row for row in wire.rows("alpha") if row["kind"] == "letter"]
    beta = [row for row in wire.rows("beta") if row["kind"] == "letter"]
    assert [(row["from"], row["to"], row["body"]) for row in alpha] == [("ada", "bob", "only alpha")]
    assert [(row["from"], row["to"], row["body"]) for row in beta] == [("bob", "ada", "only beta")]
    assert wire.rows() == []


def test_restart_preserves_registration_and_rejoin_displaces_old_identity(wire):
    wire.seed(codex_join("bob", THREAD_B), opened(2))

    async def exercise():
        async with wire.session() as client:
            checked(await client.call_tool("postbag_join", {"name": "ada"}, meta=meta()))
        async with wire.session() as client:
            checked(await client.call_tool("postbag_send", {"to": "bob", "body": "after restart"}, meta=meta()))
            takeover = checked(await client.call_tool("postbag_join", {"name": "ada"}, meta=meta(STARTUP_THREAD)))
            assert takeover["submission_state"] is None
            assert takeover["data"]["took"]["vendor"] == "codex"
            assert takeover["data"]["renamed"] is None
            assert THREAD_A not in json.dumps(takeover)
            checked(await client.call_tool("postbag_send", {"to": "bob", "body": "old sender"}, meta=meta()), ok=False)
            checked(await client.call_tool("postbag_send", {"to": "bob", "body": "new sender"}, meta=meta(STARTUP_THREAD)))
    asyncio.run(exercise())
    assert len(wire.calls()) == 2
    assert [row["body"] for row in wire.rows() if row["kind"] == "letter"] == ["after restart", "new sender"]


def test_inventory_pagination_and_bad_bag_do_not_hide_healthy_bags(wire):
    for bag in ("default", "alpha", "beta"):
        wire.seed(opened(2), bag=bag)
    wire.path("beta").write_text("{broken}\n")

    async def exercise():
        async with wire.session() as client:
            result = await client.call_tool("postbag_bags", {"limit": 2})
            data = checked(result, ok=not result.is_error)["data"]
            assert data["total"] == 3 and data["next_offset"] == 2
            assert {row["bag"] for row in data["bags"]} == {"default", "alpha"}
            result = await client.call_tool("postbag_bags", {"limit": 2, "offset": 2})
            data = checked(result, ok=not result.is_error)["data"]
            assert data["total"] == 3 and data["next_offset"] is None
            assert [row["bag"] for row in data["bags"]] == ["beta"]
            assert data["bags"][0]["peers"] is None
            assert data["errors"]
            checked(await client.call_tool("postbag_read", {"bag": "beta"}), ok=False)
            checked(await client.call_tool("postbag_read", {"bag": "alpha"}))
    asyncio.run(exercise())
    assert wire.calls() == []


def test_locked_reads_refuse_and_inventory_preserves_other_bags(wire):
    wire.seed(opened(2))
    wire.seed(opened(3), bag="busy")
    before = wire.path("busy").read_bytes()

    async def exercise():
        async with wire.session() as client:
            with wire.path("busy").open("a") as locked:
                fcntl.flock(locked, fcntl.LOCK_EX)
                reading = checked(await client.call_tool("postbag_read", {"bag": "busy"}), ok=False)
                assert reading["error_code"] == "ledger_busy"
                assert reading["submission_state"] is None
                inventory = checked(await client.call_tool("postbag_bags", {}), ok=False)["data"]
                assert inventory["total"] == 2
                rows = {row["bag"]: row for row in inventory["bags"]}
                assert rows["default"]["peers"] == []
                assert rows["busy"]["peers"] is None
                assert inventory["errors"]
                checked(await client.call_tool("postbag_read", {}))
            checked(await client.call_tool("postbag_read", {"bag": "busy"}))
    asyncio.run(exercise())
    assert wire.path("busy").read_bytes() == before
    assert wire.calls() == []


def test_native_failure_does_not_disclose_vendor_output(wire):
    wire.seed(codex_join("ada", THREAD_A), codex_join("bob", THREAD_B), opened(1))
    before = wire.path().read_bytes()

    async def exercise():
        async with wire.session(extra={"POSTBAG_TEST_EXIT": "23"}) as client:
            result = await client.call_tool("postbag_send", {"to": "bob", "body": "rejected"}, meta=meta())
            checked(result, ok=False)
            for secret in (THREAD_A, THREAD_B, "private native output"):
                assert secret not in wire_text(result)
    asyncio.run(exercise())
    assert wire.path().read_bytes() == before
    assert len(wire.calls()) == 1


def test_claude_session_environment_and_mixed_vendor_refusal(wire):
    socket_path = "/tmp/postbag-mcp-unused-test-socket"
    extra = {"CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": CLAUDE_CONVERSATION,
             "CLAUDE_CODE_MESSAGING_SOCKET": socket_path, "CLAUDE_CODE_MESSAGING_TOKEN": FAKE_TOKEN}

    async def exercise():
        async with wire.session(extra=extra) as client:
            result = await client.call_tool("postbag_join", {"name": "reader"})
            checked(result)
            for secret in (socket_path, FAKE_TOKEN, CLAUDE_CONVERSATION):
                assert secret not in wire_text(result)
            before = wire.path().read_bytes()
            checked(await client.call_tool("postbag_join", {"name": "confused"}, meta=meta()), ok=False)
            assert wire.path().read_bytes() == before
    asyncio.run(exercise())
    record = wire.rows()[0]
    assert record["vendor"] == "claude"
    assert record["socket"] == socket_path and record["token"] == FAKE_TOKEN
    assert "session_id" not in record
    assert stat.S_IMODE(wire.path().stat().st_mode) == 0o600


@pytest.mark.parametrize("partial", [
    {"CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/postbag-mcp-incomplete-socket"},
    {"CLAUDE_CODE_MESSAGING_TOKEN": FAKE_TOKEN},
])
def test_partial_claude_credentials_cannot_join_or_reach_a_door(wire, partial):
    async def exercise():
        async with wire.session(extra={"CLAUDECODE": "1", **partial}) as client:
            result = await client.call_tool("postbag_join", {"name": "reader"})
            checked(result, ok=False)
            for secret in partial.values():
                assert secret not in wire_text(result)
            checked(await client.call_tool("postbag_read", {}))
    asyncio.run(exercise())
    assert wire.rows() == []
    assert wire.calls() == []


def test_cli_and_mcp_share_durable_codex_door_identity(wire):
    wire.seed(opened(2))

    def cli(thread, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "postbag", *arguments], cwd=ROOT,
            env={**wire.environment, "CODEX_THREAD_ID": thread,
                 "CODEX_SESSION_ID": TRANSIENT_SESSION},
            capture_output=True, text=True, timeout=15,
        )

    joined = cli(THREAD_A, "join", "codex", "ada")
    assert joined.returncode == 0, joined.stderr

    async def exercise():
        async with wire.session() as client:
            checked(await client.call_tool("postbag_join", {"name": "bob"}, meta=meta(THREAD_B)))
            checked(await client.call_tool("postbag_send", {"to": "bob", "body": "MCP using CLI join"}, meta=meta()))
    asyncio.run(exercise())
    sent = cli(THREAD_B, "send", "@ada", "CLI using MCP join")
    assert sent.returncode == 0, sent.stderr
    assert [row["thread"] for row in wire.rows() if row["kind"] == "join"] == [THREAD_A, THREAD_B]
    assert [(row["from"], row["to"], row["body"]) for row in wire.rows() if row["kind"] == "letter"] == [
        ("ada", "bob", "MCP using CLI join"), ("bob", "ada", "CLI using MCP join")]
    assert TRANSIENT_SESSION not in json.dumps(wire.rows())
    assert [call[2] for call in wire.calls()] == [THREAD_B, THREAD_A]


def test_claude_socket_submission_uses_private_fake_receiver(wire):
    # Unix socket paths on macOS must remain below its much smaller path limit.
    with tempfile.TemporaryDirectory(prefix="pb-wire-", dir="/tmp") as directory:
        socket_path = str(Path(directory) / "inbox.sock")
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(socket_path)
        listener.listen(1)
        listener.settimeout(15)
        payload = []
        failures = []

        def receive():
            try:
                with listener.accept()[0] as connection:
                    connection.settimeout(15)
                    chunks = []
                    while block := connection.recv(65536):
                        chunks.append(block)
                    payload.extend(json.loads(line) for line in b"".join(chunks).decode().splitlines())
            except Exception as error:
                failures.append(error)

        thread = threading.Thread(target=receive, daemon=True)
        thread.start()
        wire.seed(codex_join("ada", THREAD_A),
                  {"kind": "join", "peer": "bob", "vendor": "claude", "socket": socket_path,
                   "token": FAKE_TOKEN}, opened(1))

        async def exercise():
            async with wire.session() as client:
                result = await client.call_tool("postbag_send", {"to": "bob", "body": "private challenge"}, meta=meta())
                assert checked(result)["submission_state"] == "submitted"
                assert socket_path not in wire_text(result) and FAKE_TOKEN not in wire_text(result)
        try:
            asyncio.run(exercise())
            thread.join(timeout=15)
            assert not thread.is_alive() and failures == []
        finally:
            listener.close()
        assert payload[0] == {"type": "auth", "token": FAKE_TOKEN}
        assert "private challenge" in payload[1]["message"]["content"]
        assert "do not send a reply" in payload[1]["message"]["content"]
        assert wire.calls() == []
