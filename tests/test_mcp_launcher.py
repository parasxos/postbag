"""The CLI launcher and dedicated MCP entry point share one stdio server."""

import asyncio
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

import postbag_mcp


TOOLS = {"postbag_join", "postbag_leave", "postbag_send", "postbag_read", "postbag_bags"}
INSTALL_HINT = "Install MCP support with: pip install 'postbag[mcp]'\n"


def test_serve_does_not_parse_the_callers_arguments(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(sys, "argv", ["postbag", "mcp", "--version", "--worker-v2", "--unexpected"])

    def unexpected_parser(*args, **kwargs):
        raise AssertionError("serve must not create an argument parser")

    monkeypatch.setattr(postbag_mcp.argparse, "ArgumentParser", unexpected_parser)
    monkeypatch.setattr(postbag_mcp, "create_server", lambda: SimpleNamespace(
        run=lambda **kwargs: calls.append(kwargs)))
    postbag_mcp.serve()
    assert calls == [{"transport": "stdio"}]
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("entry", ["serve", "main"])
def test_both_server_entries_preserve_the_missing_extra_hint(monkeypatch, capsys, entry):
    def missing_sdk():
        raise ImportError("fixture SDK missing")

    monkeypatch.setattr(sys, "argv", ["postbag-mcp"])
    monkeypatch.setattr(postbag_mcp, "create_server", missing_sdk)
    with pytest.raises(SystemExit) as error:
        getattr(postbag_mcp, entry)()
    assert error.value.code == 2
    assert capsys.readouterr() == ("", INSTALL_HINT)


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_cli_launcher_initializes_the_same_five_tool_server(tmp_path, mode):
    pytest.importorskip("mcp", reason="MCP wire checks require the optional mcp extra")
    try:
        from mcp import Client, StdioServerParameters, stdio_client
    except ImportError:
        pytest.skip("MCP wire checks require mcp 2.x")

    home = tmp_path / "home"
    home.mkdir()
    environment = {
        "HOME": str(home),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(Path(postbag_mcp.__file__).resolve().parent),
        "PYTHONDONTWRITEBYTECODE": "1",
        # These tests only list tools and inventory an empty private HOME.
        # A mistakenly added send must never resolve a native queue binary.
        "POSTBAG_CODEX": str(tmp_path / "no-such-codex"),
    }

    async def exercise():
        catalogs = []
        for name, arguments in (("dedicated", ["-m", "postbag_mcp"]),
                                ("launcher", ["-m", "postbag", "mcp"])):
            with (tmp_path / f"{name}.stderr").open("w", encoding="utf-8") as errors:
                server = StdioServerParameters(command=sys.executable, args=arguments,
                                               env=environment, cwd=tmp_path)
                async with Client(stdio_client(server, errlog=errors), mode=mode,
                                  read_timeout_seconds=15) as client:
                    tools = (await client.list_tools()).tools
                    assert len(tools) == len(TOOLS)
                    assert {tool.name for tool in tools} == TOOLS
                    catalogs.append({tool.name: tool.model_dump(mode="json") for tool in tools})
                    result = await client.call_tool("postbag_bags", {})
                    assert result.is_error is False
                    outcome = result.structured_content
                    assert outcome["ok"] is True and outcome["submission_state"] is None
                    assert outcome["data"]["version"] == postbag_mcp.postbag.__version__
                    assert outcome["data"]["bags"] == [] and outcome["data"]["total"] == 0
        assert catalogs[0] == catalogs[1]

    asyncio.run(exercise())
    assert not (home / ".postbag").exists()
