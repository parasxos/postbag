"""Wire regressions for documented MCP behaviours that test_mcp.py leaves untested.

Every claim below is taken from docs/mcp.md. The fixtures come from test_mcp:
isolated HOME, fake native executable, real SDK stdio client. Nothing here
touches ~/.postbag.
"""

import asyncio
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time

import pytest

HERE = Path(__file__).resolve().parent
MODULES = ("postbag", "postbag_mcp")
# Source layout: the modules sit beside this file and must be the ones under test.
# Installed layout (CI copies only test_mcp*.py elsewhere): both come from the environment.
SOURCE_LAYOUT = all((HERE / f"{module}.py").exists() for module in MODULES)
if SOURCE_LAYOUT and Path(importlib.util.find_spec("postbag_mcp").origin).resolve() != HERE / "postbag_mcp.py":
    sys.path.insert(0, str(HERE))
    for stale in (*MODULES, "test_mcp"):
        sys.modules.pop(stale, None)

from test_mcp import (  # noqa: E402
    CLAUDE_CONVERSATION, FAKE_TOKEN, SERVER_SCRIPT, THREAD_A, THREAD_B,
    checked, checked_read, checked_send, codex_join, letter, meta, wire, wire_text,
)

__all__ = ["wire"]


def test_server_and_ledger_modules_come_from_one_layout():
    """The server under test and its ledger module must come from the same place."""
    origins = {module: Path(importlib.util.find_spec(module).origin).resolve() for module in MODULES}
    if SOURCE_LAYOUT:
        assert origins == {module: HERE / f"{module}.py" for module in MODULES}
    else:
        assert origins["postbag"].parent == origins["postbag_mcp"].parent, origins
        assert HERE not in origins["postbag_mcp"].parents and origins["postbag_mcp"].parent != HERE
        assert Path(sys.prefix).resolve() in origins["postbag_mcp"].parents, origins
    assert SERVER_SCRIPT.resolve() == origins["postbag_mcp"]


def peers(wire, bag="default"):
    return wire.seed(codex_join("ada", THREAD_A), codex_join("bob", THREAD_B), bag=bag)


def letters(wire, bag="default"):
    return [row for row in wire.rows(bag) if row["kind"] == "letter"]


# 1. busy ledger ---------------------------------------------------------------

def test_busy_ledger_refuses_send_and_join_before_any_native_submission(wire):
    peers(wire)
    before = wire.path().read_bytes()

    async def exercise():
        async with wire.session() as client:
            with wire.path().open("a") as held:
                fcntl.flock(held, fcntl.LOCK_EX)
                sending = checked(await client.call_tool(
                    "postbag_send", {"to": "bob", "body": "while locked"}, meta=meta()), ok=False)
                assert sending["error_code"] == "ledger_busy"
                assert sending["submission_state"] == "not_submitted"
                joining = checked(await client.call_tool("postbag_join", {"name": "cy"}, meta=meta()), ok=False)
                assert joining["error_code"] == "ledger_busy"
                assert joining["submission_state"] is None
            checked(await client.call_tool("postbag_send", {"to": "bob", "body": "after unlock"}, meta=meta()))
    asyncio.run(exercise())
    assert wire.path().read_bytes().startswith(before)
    assert [row["body"] for row in letters(wire)] == ["after unlock"]
    assert len(wire.calls()) == 1


# 2. worker crashes -------------------------------------------------------------

@pytest.fixture
def parent_killer(tmp_path):
    """A fake codex that records the call, then SIGKILLs the worker that ran it."""
    script = tmp_path / "killer-codex"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, os, signal, sys\n"
        "with open(os.environ['POSTBAG_TEST_CAPTURE'], 'a') as output:\n"
        "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "os.kill(os.getppid(), signal.SIGKILL)\n",
        encoding="utf-8",
    )
    script.chmod(0o700)
    return script


def test_worker_killed_after_knock_reports_unknown_and_records_nothing(wire, parent_killer):
    peers(wire)
    before = wire.path().read_bytes()

    async def exercise():
        async with wire.session(extra={"POSTBAG_CODEX": str(parent_killer)}) as client:
            crashed = checked(await client.call_tool(
                "postbag_send", {"to": "bob", "body": "knock then die"}, meta=meta()), ok=False)
            assert crashed["error_code"] == "worker_failed"
            assert crashed["submission_state"] == "unknown"
            assert "check the recipient" in crashed["message"]
            # The dead worker released its lock; the server keeps serving and the
            # record count cannot reveal the submission that reached the native door.
            reading = checked_read(await client.call_tool("postbag_read", {}))
            assert reading["letters"] == 0
    asyncio.run(exercise())
    assert len(wire.calls()) == 1
    assert "knock then die" in wire.calls()[0][-1]
    assert wire.path().read_bytes() == before
    assert letters(wire) == []


class RawServer:
    """A stdio server driven by hand for raw protocol checks."""

    def __init__(self, wire, tmp_path, name, *, script=SERVER_SCRIPT):
        self.log = tmp_path / f"{name}.stderr"
        self.errors = self.log.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            [sys.executable, str(script)], cwd=tmp_path, env=wire.environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors,
            text=True, start_new_session=True,
        )
        self.next_id = 1

    def __enter__(self):
        response = self.request("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                               "clientInfo": {"name": "postbag-review-wire-test", "version": "1"}})
        assert "result" in response, response
        self.notify("notifications/initialized")
        return self

    def __exit__(self, *_):
        try:
            if self.process.poll() is None:
                self.process.stdin.close()
                self.process.stdin = None
                self.process.communicate(timeout=15)
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.communicate(timeout=10)
            self.errors.close()

    def notify(self, method, params=None):
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}}) + "\n")
        self.process.stdin.flush()

    def start(self, method, params):
        identifier, self.next_id = self.next_id, self.next_id + 1
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": identifier, "method": method,
                                             "params": params}) + "\n")
        self.process.stdin.flush()
        return identifier

    def response(self, identifier, timeout=30):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            assert remaining > 0, f"no response to request {identifier}: {self.log.read_text()}"
            assert self.process.poll() is None, self.log.read_text()
            if not select.select([self.process.stdout], [], [], min(remaining, 0.5))[0]:
                continue
            line = self.process.stdout.readline()
            assert line, self.log.read_text()
            message = json.loads(line)
            assert message["jsonrpc"] == "2.0"
            if message.get("id") == identifier:
                return message

    def request(self, method, params):
        return self.response(self.start(method, params))

def outcome(message):
    """The application result out of a raw tools/call response."""
    assert "result" in message, message
    body = message["result"]
    assert body["isError"] is True
    return body["structuredContent"]


def test_worker_killed_during_read_and_join_reports_worker_failed_without_state(wire, tmp_path):
    # Kill each operation once at records(), after real dispatch and before any
    # append. The marker lets later workers run normally without process polling.
    markers = tmp_path / "worker-crashes"
    markers.mkdir()
    worker = tmp_path / "crashing-worker.py"
    worker.write_text(
        "import json, os, signal, sys\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {str(SERVER_SCRIPT.parent)!r})\n"
        "import postbag_mcp as server\n"
        "request = json.load(sys.stdin)\n"
        "real_records = server.postbag.records\n"
        "def records(*args, **kwargs):\n"
        f"    marker = Path({str(markers)!r}) / request['operation']\n"
        "    if request['operation'] in {'read', 'join'} and not marker.exists():\n"
        "        marker.write_text('entered records\\n', encoding='utf-8')\n"
        "        os.kill(os.getpid(), signal.SIGKILL)\n"
        "    return real_records(*args, **kwargs)\n"
        "server.postbag.records = records\n"
        "response = server.worker(request)\n"
        "sys.stdout.buffer.write(json.dumps(response).encode('ascii') + b'\\n')\n",
        encoding="utf-8",
    )
    launcher = tmp_path / "fixture-server.py"
    launcher.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(SERVER_SCRIPT.parent)!r})\n"
        "import postbag_mcp as server\n"
        f"server.__file__ = {str(worker)!r}\n"
        "server.main()\n",
        encoding="utf-8",
    )
    wire.seed()
    before = wire.path().read_bytes()
    with RawServer(wire, tmp_path, "crash-read-join", script=launcher) as server:
        for operation, arguments in (("read", {"limit": 1}), ("join", {"name": "ada"})):
            crashed = outcome(server.request("tools/call", {
                "name": f"postbag_{operation}", "arguments": arguments, "_meta": meta(),
            }))
            assert crashed["ok"] is False
            assert crashed["error_code"] == "worker_failed"
            assert crashed["submission_state"] is None
            assert (markers / operation).read_text() == "entered records\n"

            survived = server.request("tools/call", {"name": "postbag_read", "arguments": {"limit": 1}})
            assert survived["result"]["isError"] is False
            assert survived["result"]["structuredContent"]["data"]["letters"] == 0
    assert wire.path().read_bytes() == before
    assert wire.calls() == []
    assert FAKE_TOKEN not in server.log.read_text()


# 3. cancellation ---------------------------------------------------------------

def test_cancelled_send_keeps_server_serving_and_is_recorded(wire):
    peers(wire)
    wire.seed(bag="idle")

    async def exercise():
        async with wire.session(extra={"POSTBAG_TEST_SLEEP": "2"}) as client:
            call = asyncio.create_task(client.call_tool(
                "postbag_send", {"to": "bob", "body": "cancelled but delivered"}, meta=meta()))
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 10
            while not wire.calls():
                assert loop.time() < deadline, "fake transport never received the letter"
                await asyncio.sleep(0.02)
            call.cancel()
            with pytest.raises(asyncio.CancelledError):
                await call
            # The same session answers immediately while the detached worker still runs.
            idle = checked(await client.call_tool("postbag_read", {"bag": "idle"}))["data"]
            assert idle["letters"] == 0
            deadline = loop.time() + 15
            while True:
                result = await client.call_tool("postbag_read", {})
                value = result.structured_content
                if value["ok"]:
                    break
                assert value["error_code"] == "ledger_busy", value
                assert loop.time() < deadline, "the cancelled send never finished recording"
                await asyncio.sleep(0.1)
            data = checked(result)["data"]
            assert data["letters"] == 1
            assert [row["body"] for row in data["records"] if row["kind"] == "letter"] == ["cancelled but delivered"]
    asyncio.run(exercise())
    assert len(wire.calls()) == 1
    assert [row["body"] for row in letters(wire)] == ["cancelled but delivered"]


# 4. POSTBAG_LEDGER is ignored --------------------------------------------------

def test_server_environment_ledger_override_is_ignored(wire, tmp_path):
    elsewhere = tmp_path / "elsewhere" / "ledger.jsonl"

    async def exercise():
        async with wire.session(extra={"POSTBAG_LEDGER": str(elsewhere)}) as client:
            checked(await client.call_tool("postbag_join", {"name": "ada"}, meta=meta()))
            data = checked(await client.call_tool("postbag_read", {}))["data"]
            assert data["peers"] == [{"name": "ada", "vendor": "codex"}]
    asyncio.run(exercise())
    assert [row["peer"] for row in wire.rows() if row["kind"] == "join"] == ["ada"]
    assert not elsewhere.exists() and not elsewhere.parent.exists()
    assert wire.calls() == []


# 5. hostile PYTHONPATH --------------------------------------------------------

def test_workers_ignore_hostile_pythonpath(wire, tmp_path):
    hostile = tmp_path / "hostile"
    hostile.mkdir()
    marker = tmp_path / "hostile-import-executed"
    (hostile / "postbag.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('imported')\n"
        "raise RuntimeError('hostile postbag imported')\n",
        encoding="utf-8",
    )
    wire.seed()

    async def exercise():
        # Pinned entry point: the claim under test is worker resolution, and the
        # server's own import order (script directory first) keeps it healthy.
        async with wire.session(extra={"PYTHONPATH": f"{hostile}{os.pathsep}{SERVER_SCRIPT.parent}"}, pinned=True) as client:
            checked(await client.call_tool("postbag_join", {"name": "ada"}, meta=meta()))
            checked(await client.call_tool("postbag_join", {"name": "bob"}, meta=meta(THREAD_B)))
            checked(await client.call_tool("postbag_send", {"to": "bob", "body": "clean import"}, meta=meta()))
            checked(await client.call_tool("postbag_read", {}))
            checked(await client.call_tool("postbag_bags", {}))
    asyncio.run(exercise())
    assert not marker.exists(), "a worker imported postbag from PYTHONPATH"
    assert [row["body"] for row in letters(wire)] == ["clean import"]
    assert len(wire.calls()) == 1


# 6. identity refusals on send -------------------------------------------------

CLAUDE_INBOX = {"CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/postbag-review-unused-socket",
                "CLAUDE_CODE_MESSAGING_TOKEN": FAKE_TOKEN}


@pytest.mark.parametrize("extra,metadata,reason", [
    ({"CLAUDECODE": "1", **CLAUDE_INBOX}, meta(), "threadId plus a complete Claude inbox is ambiguous"),
    ({}, None, "no metadata and no Claude inbox"),
    (CLAUDE_INBOX, None, "inbox without CLAUDECODE or CLAUDE_CODE_SESSION_ID"),
])
def test_send_without_a_single_trusted_identity_is_refused(wire, extra, metadata, reason):
    peers(wire)
    before = wire.path().read_bytes()

    async def exercise():
        async with wire.session(extra=extra) as client:
            result = await client.call_tool("postbag_send", {"to": "bob", "body": "who am I"}, meta=metadata)
            refused = checked(result, ok=False)
            assert refused["error_code"] == "identity_unavailable", reason
            assert refused["submission_state"] == "not_submitted", reason
            assert FAKE_TOKEN not in wire_text(result)
            assert CLAUDE_INBOX["CLAUDE_CODE_MESSAGING_SOCKET"] not in wire_text(result)
    asyncio.run(exercise())
    assert wire.path().read_bytes() == before
    assert wire.calls() == []


# 7. unknown arguments on read and bags ----------------------------------------

@pytest.mark.parametrize("tool,arguments", [
    ("postbag_read", {"limit": 5, "extra": "unrecognized"}),
    ("postbag_read", {"bag": "default", "vendor": "codex"}),
    ("postbag_bags", {"offset": 0, "bag": "default"}),
    ("postbag_bags", {"threadId": THREAD_B}),
])
def test_unknown_arguments_on_read_and_bags_are_refused(wire, tool, arguments):
    wire.seed()
    before = wire.path().read_bytes()

    async def exercise():
        async with wire.session() as client:
            refused = checked(await client.call_tool(tool, arguments, meta=meta()), ok=False)
            assert refused["error_code"] == "invalid_input"
            assert refused["submission_state"] is None
            assert "unknown tool arguments" in refused["message"]
            reading = checked_read(await client.call_tool("postbag_read", {}))
            assert reading["bag"] == "default" and reading["records"] == []
    asyncio.run(exercise())
    assert wire.path().read_bytes() == before
    assert wire.calls() == []


# 8. takeover receipts -----------------------------------------------------------

def test_join_receipts_report_takeover_and_rename(wire):
    async def exercise():
        async with wire.session() as client:
            first = await client.call_tool("postbag_join", {"name": "ada"}, meta=meta(THREAD_A))
            data = checked(first)["data"]
            assert data["took"] is None and data["renamed"] is None
            assert data["name"] == "ada" and data["vendor"] == "codex"

            takeover = await client.call_tool("postbag_join", {"name": "ada"}, meta=meta(THREAD_B))
            data = checked(takeover)["data"]
            assert data["renamed"] is None
            assert set(data["took"]) == {"vendor", "at"}
            assert data["took"]["vendor"] == "codex"
            assert isinstance(data["took"]["at"], str) and data["took"]["at"]

            rename = await client.call_tool("postbag_join", {"name": "bea"}, meta=meta(THREAD_B))
            data = checked(rename)["data"]
            assert data["renamed"] == "ada"
            assert data["took"] is None

            for result in (first, takeover, rename):
                assert THREAD_A not in wire_text(result) and THREAD_B not in wire_text(result)
            peers = checked(await client.call_tool("postbag_read", {}))["data"]["peers"]
            assert peers == [{"name": "bea", "vendor": "codex"}]
    asyncio.run(exercise())
    assert [row["thread"] for row in wire.rows() if row["kind"] == "join"] == [THREAD_A, THREAD_B, THREAD_B]
    assert wire.calls() == []


# 9. final letters ---------------------------------------------------------------

def test_final_letter_announces_no_reply_and_next_send_remains_legal(wire):
    peers(wire)

    async def exercise():
        async with wire.session() as client:
            last = checked_send(await client.call_tool("postbag_send", {
                "to": "bob", "body": "final", "final": True}, meta=meta()), final=True)
            assert last["data"]["letter"] == 1
            followup = checked_send(await client.call_tool("postbag_send", {
                "to": "ada", "body": "a separate task"}, meta=meta(THREAD_B)))
            assert followup["data"]["letter"] == 2
    asyncio.run(exercise())
    assert len(wire.calls()) == 2
    assert [row["body"] for row in letters(wire)] == ["final", "a separate task"]
    assert letters(wire)[0]["final"] is True and "final" not in letters(wire)[1]
    assert "Final letter. Do not reply to this letter" in wire.calls()[0][-1]
    assert "call postbag_send" in wire.calls()[1][-1]


# 10. leading @ in `to` ------------------------------------------------------------

def test_recipient_mention_is_accepted_and_normalised(wire):
    peers(wire)

    async def exercise():
        async with wire.session() as client:
            sent = checked(await client.call_tool("postbag_send", {"to": "@bob", "body": "mentioned"}, meta=meta()))
            assert sent["data"]["to"] == "bob"
            assert sent["data"]["from"] == "ada"
            assert "@bob" in sent["message"]
    asyncio.run(exercise())
    assert [(row["from"], row["to"]) for row in letters(wire)] == [("ada", "bob")]
    assert wire.calls()[0][2] == THREAD_B


# 11. partial inventory ------------------------------------------------------------

def test_unreadable_named_bags_yield_incomplete_inventory_with_healthy_rows(wire):
    wire.seed()
    wire.seed(codex_join("ada", THREAD_A), letter("private inventory body"), bag="healthy")
    bags = wire.home / ".postbag" / "bags"
    (bags / "folder.jsonl").mkdir()
    dark = bags / "dark.jsonl"
    dark.write_text("")
    dark.chmod(0)
    unreadable = {"folder"} | ({"dark"} if os.geteuid() != 0 else set())

    async def exercise():
        async with wire.session() as client:
            result = await client.call_tool("postbag_bags", {})
            partial = checked(result, ok=False)
            assert partial["error_code"] == "inventory_incomplete"
            assert partial["submission_state"] is None
            data = partial["data"]
            rows = {row["bag"]: row for row in data["bags"]}
            assert data["total"] == 4 and data["next_offset"] is None
            assert rows["healthy"] == {"bag": "healthy", "letters": 1, "last_letter": "2026-09-30T10:00:00+00:00",
                                       "peers": [{"name": "ada", "vendor": "codex"}]}
            assert rows["default"]["peers"] == [] and rows["default"]["letters"] == 0
            for label in unreadable:
                assert rows[label]["letters"] is None and rows[label]["peers"] is None
            assert len(data["errors"]) >= len(unreadable)
            assert all(isinstance(problem, str) and problem for problem in data["errors"])
            assert THREAD_A not in wire_text(result)
            assert "private inventory body" not in wire_text(result)
            assert all(set(row) == {"bag", "letters", "last_letter", "peers"} for row in rows.values())
            checked(await client.call_tool("postbag_read", {"bag": "healthy"}))
    asyncio.run(exercise())
    assert wire.calls() == []


# 12. recovery metadata on send refusals ----------------------------------------

GONE_SOCKET = object()  # replaced per test with a path under its private tmp directory
SUFFIX = "; stop and ask the human"


def claude_join(name, socket_path):
    return {"kind": "join", "peer": name, "vendor": "claude", "socket": socket_path, "token": FAKE_TOKEN}


RECOVERY_CASES = {
    "not joined": (
        [codex_join("bob", THREAD_B)], "default",
        {"action": "join", "actor": "caller", "bag": "default", "vendor": "codex", "name": None},
        "refused"),
    "unregistered recipient": (
        [codex_join("ada", THREAD_A)], "default",
        {"action": "read", "actor": "caller", "bag": "default"}, "refused"),
    "recipient door gone": (
        [codex_join("ada", THREAD_A), claude_join("bob", GONE_SOCKET)], "default",
        {"action": "join", "actor": "recipient", "bag": "default", "vendor": "claude", "name": "bob"},
        "transport_unavailable"),
    "missing bag": (
        [], "nowhere", {"action": "join", "actor": "caller", "bag": "nowhere",
                        "vendor": "codex", "name": None}, "refused"),
}


@pytest.mark.parametrize("case", sorted(RECOVERY_CASES))
def test_send_refusals_carry_recovery_metadata(wire, tmp_path, case):
    records, bag, recovery, code = RECOVERY_CASES[case]
    gone_socket = str(tmp_path / "gone-inbox.sock")
    records = [{**row, "socket": gone_socket} if row.get("socket") is GONE_SOCKET else row for row in records]
    if records:
        wire.seed(*records)
    before = wire.path().read_bytes() if records else b""

    async def exercise():
        async with wire.session() as client:
            result = await client.call_tool("postbag_send", {"to": "bob", "body": "hello", "bag": bag}, meta=meta())
            refused = checked(result, ok=False)
            assert refused["error_code"] == code
            assert refused["submission_state"] == "not_submitted"
            assert refused["data"] == {"recovery": recovery}
            assert refused["data"]["recovery"]["actor"] == recovery["actor"]
            message = refused["message"]
            assert message.endswith(SUFFIX), message
            # Only the recipient may ever be told to join under the recipient's name.
            if 'name="bob"' in message:
                assert recovery["actor"] == "recipient"
                assert message.index("have that recipient") < message.index('name="bob"')
            assert "To register, call postbag_join" not in message
            assert "join claude bob" not in message or recovery["actor"] == "recipient"
            for secret in (THREAD_A, THREAD_B, FAKE_TOKEN, gone_socket):
                assert secret not in wire_text(result)
    asyncio.run(exercise())
    if records:
        assert wire.path().read_bytes() == before
    assert not wire.path("nowhere").exists()
    assert wire.calls() == []


def test_join_description_and_instructions_say_shared_inbox_is_one_peer(wire):
    async def exercise():
        async with wire.session() as client:
            assert "Claude subagents sharing an inbox use the parent's peer" in client.instructions
            instructions = client.instructions.lower()
            assert "joining creates the selected bag" in instructions
            assert "do not reply to a final letter" in instructions
            assert "human opens" not in instructions and "budget" not in instructions
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            assert "Claude subagents sharing an inbox are the same peer" in tools["postbag_join"].description
    asyncio.run(exercise())
    assert not (wire.home / ".postbag").exists()
