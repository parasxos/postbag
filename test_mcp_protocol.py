"""Worker protocol compatibility over private subprocesses and real MCP stdio.

The compact legacy fixture preserves the 1.4.0 argparse entry contract from
4b66bac. It is deliberately not a second implementation of the old server.
"""

import asyncio
from contextlib import asynccontextmanager
import json
import select
import subprocess
import sys

import pytest

pytest.importorskip("mcp", reason="MCP wire checks require the optional mcp extra")
try:
    from mcp import Client, StdioServerParameters, stdio_client
except ImportError:
    pytest.skip("MCP wire checks require mcp 2.x", allow_module_level=True)

from test_mcp import (
    FAKE_TOKEN, SERVER_SCRIPT, THREAD_A, THREAD_B, checked, codex_join, meta,
    wire, wire_text,
)
import postbag_mcp


CALLS = [
    ("join", {"name": "ada", "bag": "default"}),
    ("send", {"to": "bob", "body": "protocol fixture", "bag": "default", "final": True}),
    ("read", {"bag": "default", "limit": 20, "before": None}),
    ("bags", {"limit": 50, "offset": 0}),
    ("leave", {"bag": "default"}),
]


def seed_peers(wire):
    wire.seed(codex_join("ada", THREAD_A), codex_join("bob", THREAD_B))
    return wire.path().read_bytes()


@asynccontextmanager
async def replaced_worker(wire, tmp_path, source):
    worker = tmp_path / "fixture-worker.py"
    worker.write_text(source, encoding="utf-8")
    launcher = tmp_path / "fixture-server.py"
    launcher.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(SERVER_SCRIPT.parent)!r})\n"
        "import postbag_mcp as server\n"
        f"server.__file__ = {str(worker)!r}\n"
        "server.main()\n",
        encoding="utf-8",
    )
    log = tmp_path / "server.stderr"
    with log.open("w", encoding="utf-8") as errors:
        async with Client(stdio_client(StdioServerParameters(
            command=sys.executable, args=[str(launcher)], cwd=tmp_path,
            env=wire.environment), errlog=errors), read_timeout_seconds=15) as client:
            yield client
    assert FAKE_TOKEN not in log.read_text()
    assert "private native output" not in log.read_text()


def mismatch(output):
    """The old parent requires successful process exit and a JSON outcome."""
    value = json.loads(output.decode("ascii"))
    assert set(value) == {"ok", "error_code", "submission_state", "message", "data"}
    assert value["ok"] is False
    assert value["error_code"] == "worker_version_mismatch"
    assert value["submission_state"] == "not_submitted"
    assert "reconnect" in value["message"].lower()
    assert value["message"].endswith("stop and ask the human")
    assert value["data"] == {}
    return value


def test_worker_protocol_has_an_explicit_major_version():
    assert postbag_mcp.WORKER_PROTOCOL == 2


@pytest.mark.parametrize("operation,arguments", CALLS)
def test_legacy_worker_mode_returns_a_pre_dispatch_refusal(wire, tmp_path, operation, arguments):
    before = seed_peers(wire)
    request = {"operation": operation, "arguments": arguments, "vendor": "codex"}
    completed = subprocess.run(
        [sys.executable, "-E", "-s", str(SERVER_SCRIPT), "--worker"],
        input=json.dumps(request).encode("ascii"), capture_output=True,
        cwd=tmp_path, env=wire.environment, timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    mismatch(completed.stdout)
    assert wire.path().read_bytes() == before
    assert wire.calls() == []


@pytest.mark.parametrize("input_bytes", [
    b"", b"not-json\xff", json.dumps({
        "operation": "send", "vendor": "codex", "arguments": {
            "bag": "missing", "to": "bob", "body": "x" * 65536, "final": True,
        },
    }).encode("ascii"),
], ids=["empty", "invalid_json_and_encoding", "maximum_body"])
def test_legacy_worker_refusal_does_not_require_valid_input(wire, tmp_path, input_bytes):
    completed = subprocess.run(
        [sys.executable, "-E", "-s", str(SERVER_SCRIPT), "--worker"],
        input=input_bytes, capture_output=True, cwd=tmp_path,
        env=wire.environment, timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    mismatch(completed.stdout)
    assert not (wire.home / ".postbag").exists()
    assert wire.calls() == []


def test_legacy_worker_refuses_without_waiting_for_stdin(wire, tmp_path):
    process = subprocess.Popen(
        [sys.executable, "-E", "-s", str(SERVER_SCRIPT), "--worker"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=tmp_path, env=wire.environment, start_new_session=True,
    )
    try:
        # Keep stdin open and send nothing: the gate must precede json.load.
        assert select.select([process.stdout], [], [], 5)[0], "legacy mode waited for stdin"
        mismatch(process.stdout.readline())
        process.communicate(timeout=5)
        assert process.returncode == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
    assert not (wire.home / ".postbag").exists()
    assert wire.calls() == []


@pytest.mark.parametrize("operation,arguments", CALLS)
def test_new_parent_does_not_fall_back_to_a_legacy_worker(wire, tmp_path, operation, arguments):
    before = seed_peers(wire)
    attempts, dispatched = tmp_path / "argv.jsonl", tmp_path / "legacy-dispatch"
    # These options match 1.4.0 main(). The dispatch marker would catch a
    # fallback to --worker, which would silently lose the final argument.
    source = (
        "import argparse, json, sys\n"
        "from pathlib import Path\n"
        f"with open({str(attempts)!r}, 'a') as output:\n"
        "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "parser = argparse.ArgumentParser(description='Postbag local MCP tools over stdio')\n"
        "parser.add_argument('--version', action='version', version='postbag-mcp 1.4.0')\n"
        "parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)\n"
        "args = parser.parse_args()\n"
        "if args.worker:\n"
        f"    Path({str(dispatched)!r}).write_text('legacy worker dispatched')\n"
    )

    async def exercise():
        async with replaced_worker(wire, tmp_path, source) as client:
            response = await client.call_tool(f"postbag_{operation}", arguments, meta=meta())
            value = checked(response, ok=False)
            assert value["error_code"] == "worker_failed"
            assert value["submission_state"] == ("unknown" if operation == "send" else None)
            assert "reconnect" in value["message"].lower()
            assert "unrecognized arguments" not in wire_text(response)
    asyncio.run(exercise())
    assert [json.loads(line) for line in attempts.read_text().splitlines()] == [["--worker-v2"]]
    assert not dispatched.exists()
    assert wire.path().read_bytes() == before
    assert wire.calls() == []


@pytest.mark.parametrize("after_submission", [False, True], ids=["before_submission", "after_submission"])
def test_exit_two_without_json_remains_unknown(wire, tmp_path, after_submission):
    before = seed_peers(wire)
    source = (
        "import json, os, subprocess, sys\n"
        f"sys.path.insert(0, {str(SERVER_SCRIPT.parent)!r})\n"
        "import postbag_mcp as server\n"
        "assert sys.argv[1:] == ['--worker-v2']\n"
        "request = json.load(sys.stdin)\n"
        "if request['operation'] == 'send':\n"
        f"    if {after_submission!r}:\n"
        "        subprocess.run([os.environ['POSTBAG_CODEX'], 'queue', '--thread',\n"
        f"                        {THREAD_B!r}, '--message', 'protocol fixture'], check=True)\n"
        "    os._exit(2)\n"
        "sys.stdout.buffer.write(json.dumps(server.worker(request)).encode('ascii') + b'\\n')\n"
    )

    async def exercise():
        async with replaced_worker(wire, tmp_path, source) as client:
            response = await client.call_tool("postbag_send", {
                "to": "bob", "body": "protocol fixture", "final": True,
            }, meta=meta())
            value = checked(response, ok=False)
            assert value["error_code"] == "worker_failed"
            assert value["submission_state"] == "unknown"
            assert "check the recipient" in value["message"].lower()
            assert "private native output" not in wire_text(response)
            checked(await client.call_tool("postbag_read", {}))
    asyncio.run(exercise())
    assert wire.path().read_bytes() == before
    assert len(wire.calls()) == int(after_submission)
