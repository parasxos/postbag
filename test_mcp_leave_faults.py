"""Leave failures can change the roster even when no result reaches the caller."""

import asyncio
from contextlib import asynccontextmanager
import sys

import pytest

from test_mcp_leave import SERVER_SCRIPT, THREAD_A, checked, checked_read, codex_join, meta, wire
from test_mcp import Client, StdioServerParameters, stdio_client

__all__ = ["wire"]


@asynccontextmanager
async def interrupted_leave(wire, tmp_path, mode):
    entered, release = tmp_path / "entered", tmp_path / "release"
    worker = tmp_path / "interrupted-worker.py"
    worker.write_text(
        "import json, os, sys, time\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {str(SERVER_SCRIPT.parent)!r})\n"
        "import postbag_mcp as server\n"
        "request = json.load(sys.stdin)\n"
        "real_fsync = os.fsync\n"
        "def interrupted(fd):\n"
        f"    Path({str(entered)!r}).write_text('append flushed')\n"
        f"    mode = {mode!r}\n"
        "    if mode == 'crash':\n"
        "        os._exit(17)\n"
        "    if mode == 'fail':\n"
        "        raise OSError('injected fsync failure')\n"
        "    deadline = time.monotonic() + 10\n"
        f"    while not Path({str(release)!r}).exists():\n"
        "        if time.monotonic() > deadline:\n"
        "            raise OSError('fixture release deadline')\n"
        "        time.sleep(0.01)\n"
        "    return real_fsync(fd)\n"
        "if request['operation'] == 'leave':\n"
        "    server.postbag.os.fsync = interrupted\n"
        "response = server.worker(request)\n"
        "sys.stdout.buffer.write(json.dumps(response).encode('ascii') + b'\\n')\n",
        encoding="utf-8")
    launcher = tmp_path / "fixture-server.py"
    launcher.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(SERVER_SCRIPT.parent)!r})\n"
        "import postbag_mcp as server\n"
        # Workers locates its entrypoint from realpath(__file__). Replace only that path.
        f"server.__file__ = {str(worker)!r}\n"
        "server.main()\n", encoding="utf-8")
    with (tmp_path / "server.stderr").open("w", encoding="utf-8") as errors:
        async with Client(stdio_client(StdioServerParameters(
            command=sys.executable, args=[str(launcher)], cwd=tmp_path,
            env=wire.environment), errlog=errors), read_timeout_seconds=15) as client:
            try:
                yield client, entered, release
            finally:
                release.touch()


@pytest.mark.parametrize("mode,code", [("fail", "recording_failed"), ("crash", "worker_failed")])
def test_leave_failure_after_append_requires_reading_actual_roster(wire, tmp_path, mode, code):
    wire.seed(codex_join("ada", THREAD_A))

    async def exercise():
        async with interrupted_leave(wire, tmp_path, mode) as (client, entered, _):
            value = checked(await client.call_tool("postbag_leave", {}, meta=meta()), ok=False)
            assert entered.exists()
            assert value["error_code"] == code
            assert value["submission_state"] is None
            if mode == "fail":
                assert value["data"]["recovery"] == {"action": "read", "actor": "caller", "bag": "default"}
                assert "could not be confirmed" in value["message"]
            else:
                assert "Read the bag to determine its current state" in value["message"]
            assert "postbag_join" not in value["message"]
            data = checked_read(await client.call_tool("postbag_read", {}))
            assert data["peers"] == [] and data["letters"] == 0
            assert [rec["kind"] for rec in data["records"]] == ["join", "leave"]
    asyncio.run(exercise())
    assert len(wire.rows()) == 2
    assert wire.calls() == []


def test_cancelled_leave_finishes_and_same_server_reports_withdrawal(wire, tmp_path):
    wire.seed(codex_join("ada", THREAD_A))
    wire.seed(bag="idle")

    async def exercise():
        async with interrupted_leave(wire, tmp_path, "pause") as (client, entered, release):
            call = asyncio.create_task(client.call_tool("postbag_leave", {}, meta=meta()))
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 10
            while not entered.exists():
                assert loop.time() < deadline, "leave never reached its fsync"
                await asyncio.sleep(0.01)
            call.cancel()
            with pytest.raises(asyncio.CancelledError):
                await call
            checked_read(await client.call_tool("postbag_read", {"bag": "idle"}))
            busy = checked(await client.call_tool("postbag_read", {}), ok=False)
            assert busy["error_code"] == "ledger_busy"
            release.touch()
            while True:
                response = await client.call_tool("postbag_read", {})
                if not response.is_error:
                    data = checked_read(response)
                    break
                assert checked(response, ok=False)["error_code"] == "ledger_busy"
                assert loop.time() < deadline, "leave did not release the ledger"
                await asyncio.sleep(0.01)
            assert data["peers"] == [] and data["letters"] == 0
            assert [row["kind"] for row in data["records"]] == ["join", "leave"]
    asyncio.run(exercise())
    assert len(wire.rows()) == 2
    assert wire.calls() == []
