"""Resume hints use optional join metadata, with private CLI fixtures only."""

import json
import re
import socket
import subprocess
import sys
import tempfile
import threading

import pytest

from test_inventory import SCRIPT, fingerprint, inventory_cli, joined, opened, seed
from test_inventory_terminal import NOW, WRAPPER, plain


FIRST = "123e4567-e89b-12d3-a456-426614174000"
SECOND = "abcde123-4567-4890-abcd-1234567890ab"
THIRD = "fedcba98-7654-4321-9876-abcdef012345"
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
COMMAND = re.compile(rf"claude --resume ({UUID})(?![0-9a-f-])")


def succeeded(result):
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    return result.stdout


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def claude(peer="ada", session_id=FIRST, *, door="fake-claude-door", legacy=False):
    record = joined(peer, "claude", door, legacy=legacy)
    record["session_id"] = session_id
    return record


def resume(cli):
    return succeeded(cli.run("bags", "--resume"))


def unknown(text):
    assert "session id" in " ".join(text.lower().split())
    assert "rejoin" in text.lower()


@pytest.mark.parametrize("value", [FIRST, SECOND.upper(), "00000000-0000-0000-0000-000000000000"])
def test_claude_join_captures_and_normalizes_optional_session_id(inventory_cli, value):
    cli = inventory_cli
    text = succeeded(cli.run("join", "claude", "ada", extra={"CLAUDE_CODE_SESSION_ID": value}))
    record = rows(cli.default)[-1]
    assert record["session_id"] == value.lower()
    assert record["socket"] == cli.environment["CLAUDE_CODE_MESSAGING_SOCKET"]
    assert record["token"] == cli.environment["CLAUDE_CODE_MESSAGING_TOKEN"]
    assert value.lower() not in text.lower()


@pytest.mark.parametrize("value", [
    None, "", "not-a-uuid", FIRST.replace("-", ""), "{" + FIRST + "}",
    "urn:uuid:" + FIRST, " " + FIRST, FIRST + " ", FIRST + "\n",
    FIRST + "; touch unexpected-marker", FIRST + "\x1b[2J",
], ids=["missing", "empty", "invalid", "unhyphenated", "braced", "urn", "leading-space",
        "trailing-space", "newline", "shell", "escape"])
def test_invalid_optional_environment_does_not_break_join_or_persist(inventory_cli, value):
    cli = inventory_cli
    extra = {} if value is None else {"CLAUDE_CODE_SESSION_ID": value}
    succeeded(cli.run("join", "claude", extra=extra))
    record = rows(cli.default)[-1]
    assert record["peer"] == "claude"
    assert "session_id" not in record
    text = resume(cli)
    assert not COMMAND.search(text)
    unknown(text)


def test_codex_join_never_captures_claude_session_metadata(inventory_cli):
    cli = inventory_cli
    succeeded(cli.run("join", "codex", "bob", extra={"CLAUDE_CODE_SESSION_ID": FIRST}))
    record = rows(cli.default)[-1]
    assert "session_id" not in record
    text = resume(cli)
    assert FIRST not in text
    assert not COMMAND.search(text)


def test_resume_is_opt_in_and_excludes_codex_metadata(inventory_cli):
    cli = inventory_cli
    codex = joined("bob")
    codex["session_id"] = SECOND
    seed(cli.default, opened(4), claude(), codex)
    before = fingerprint(cli.default)
    for args in (("bags",), ("read",), ("read", "1")):
        text = succeeded(cli.run(*args))
        assert FIRST not in text and SECOND not in text
        assert "claude --resume" not in text
    text = resume(cli)
    assert COMMAND.findall(text) == [FIRST]
    assert SECOND not in text
    assert "@ada" in text
    assert "conversation" in text.lower() and "join" in text.lower()
    assert fingerprint(cli.default) == before


@pytest.mark.parametrize("value", [
    None, "", 123, True, [FIRST], {"session_id": FIRST},
    FIRST.replace("-", ""), "{" + FIRST + "}", "urn:uuid:" + FIRST,
    FIRST + "; touch unexpected-marker", FIRST + "\nforged output", FIRST + "\x1b[2J",
])
def test_malformed_metadata_is_unknown_without_breaking_legacy_reads(inventory_cli, value):
    cli = inventory_cli
    seed(cli.default, opened(2), claude(session_id=value))
    before = fingerprint(cli.default)
    for args in (("read",), ("bags",), ("bags", "--resume")):
        text = succeeded(cli.run(*args))
        assert FIRST not in text
        assert "unexpected-marker" not in text and "forged output" not in text
        assert "\x1b" not in text
        assert not COMMAND.search(text)
    unknown(text)
    assert fingerprint(cli.default) == before
    assert not (cli.cwd / "unexpected-marker").exists()


@pytest.mark.parametrize("legacy", [False, True])
def test_join_without_metadata_remains_readable_and_unknown(inventory_cli, legacy):
    cli = inventory_cli
    seed(cli.default, joined("claude", "claude", legacy=legacy))
    succeeded(cli.run("read"))
    text = resume(cli)
    assert "@claude" in text
    assert not COMMAND.search(text)
    unknown(text)


def test_latest_real_rejoin_replaces_or_clears_metadata_without_changing_door(inventory_cli):
    cli = inventory_cli
    for value, expected in ((FIRST, [FIRST]), (SECOND.upper(), [SECOND]), (None, [])):
        extra = {} if value is None else {"CLAUDE_CODE_SESSION_ID": value}
        succeeded(cli.run("join", "claude", "ada", extra=extra))
        text = resume(cli)
        assert COMMAND.findall(text) == expected
        if not expected:
            unknown(text)
    registered = rows(cli.default)
    assert len(registered) == 3
    assert len({(r["socket"], r["token"]) for r in registered}) == 1
    assert "session_id" not in registered[-1]
    assert FIRST not in succeeded(cli.run("read"))
    assert SECOND not in succeeded(cli.run("read"))


def test_rename_and_takeover_use_only_current_join_metadata(inventory_cli):
    cli = inventory_cli
    seed(cli.default,
         claude("ada", FIRST, door="same-door"),
         claude("bob", SECOND, door="same-door"),
         claude("bob", THIRD, door="replacement-door"))
    text = resume(cli)
    assert COMMAND.findall(text) == [THIRD]
    assert FIRST not in text and SECOND not in text
    assert "@ada" not in text and "@bob" in text


def test_capture_metadata_does_not_turn_a_rename_into_a_second_door(inventory_cli):
    cli = inventory_cli
    succeeded(cli.run("join", "claude", "ada", extra={"CLAUDE_CODE_SESSION_ID": FIRST}))
    succeeded(cli.run("join", "claude", "bob", extra={"CLAUDE_CODE_SESSION_ID": SECOND}))
    text = resume(cli)
    assert COMMAND.findall(text) == [SECOND]
    assert FIRST not in text and "@ada" not in text
    assert "@bob" in text


def test_changed_optional_session_id_keeps_sender_identity_and_native_routing(inventory_cli):
    cli = inventory_cli
    sender = claude("ada", FIRST, door=cli.environment["CLAUDE_CODE_MESSAGING_TOKEN"])
    target = claude("bob", THIRD, door="different-fake-token")
    received, failures = [], []
    # macOS limits Unix socket paths below pytest's full temporary pathname.
    with tempfile.TemporaryDirectory(prefix="pb-resume-", dir="/tmp") as short, \
            socket.socket(socket.AF_UNIX) as listener:
        target["socket"] = short + "/recipient.sock"
        seed(cli.default, opened(2), sender, target)
        listener.bind(target["socket"])
        listener.listen(1)
        listener.settimeout(2)

        def receive():
            try:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(2)
                    content = b""
                    while chunk := connection.recv(8192):
                        content += chunk
                received.extend(json.loads(line) for line in content.splitlines())
            except Exception as error:
                failures.append(error)

        worker = threading.Thread(target=receive, daemon=True)
        worker.start()
        result = cli.run("send", "@bob", "routing fixture", extra={"CLAUDE_CODE_SESSION_ID": SECOND})
        worker.join(timeout=3)
        succeeded(result)
        assert not worker.is_alive() and not failures
    assert received[0] == {"type": "auth", "token": target["token"]}
    assert "from @ada to @bob" in received[1]["message"]["content"]
    assert all(value not in received[1]["message"]["content"] for value in (FIRST, SECOND, THIRD))
    last = rows(cli.default)[-1]
    assert last["kind"] == "letter" and last["from"] == "ada" and last["to"] == "bob"


@pytest.mark.parametrize("columns", [None, 40, 120], ids=["pipe", "narrow-terminal", "wide-terminal"])
def test_resume_display_never_opens_registry_or_contacts_native_transport(inventory_cli, columns):
    cli = inventory_cli
    seed(cli.default, opened(2), claude(session_id=FIRST.upper()))
    for directory in (".claude", ".codex"):
        registry = cli.home / directory / "registry.json"
        registry.parent.mkdir()
        registry.write_text(json.dumps({"session_id": SECOND}), encoding="utf-8")
    paths = sorted(path for path in cli.home.rglob("*") if path.is_file())
    before = {path: fingerprint(path) for path in paths}
    wrapper = r"""
import os, pathlib, runpy, sys
home = pathlib.Path(os.environ['HOME'])
forbidden = (str(home / '.claude'), str(home / '.codex'))
class Output:
    def __init__(self, stream):
        self.stream = stream
    def isatty(self):
        return os.environ['POSTBAG_TEST_TTY'] == '1'
    def __getattr__(self, name):
        return getattr(self.stream, name)
sys.stdout = Output(sys.stdout)
def audit(event, args):
    if event in ('subprocess.Popen', 'socket.connect'):
        raise AssertionError('resume display attempted a native call')
    if event in ('open', 'os.listdir', 'os.scandir') and args and isinstance(args[0], (str, bytes)):
        path = os.fsdecode(args[0])
        if any(path == root or path.startswith(root + os.sep) for root in forbidden):
            raise AssertionError('resume display read a registry or transcript')
sys.addaudithook(audit)
sys.argv = [sys.argv[1], 'bags', '--resume']
runpy.run_path(sys.argv[0], run_name='__main__')
"""
    result = subprocess.run(
        [sys.executable, "-c", wrapper, str(SCRIPT)], cwd=cli.cwd,
        env={**cli.environment, "POSTBAG_TEST_TTY": str(int(columns is not None)),
             "COLUMNS": str(columns or 80), "NO_COLOR": ""},
        capture_output=True, text=True, timeout=3,
    )
    assert COMMAND.findall(succeeded(result)) == [FIRST]
    assert SECOND not in result.stdout
    assert {path: fingerprint(path) for path in paths} == before
    assert sorted(path for path in cli.home.rglob("*") if path.is_file()) == paths


def test_resume_preserves_inventory_scope_and_does_not_create_missing_bags(inventory_cli):
    cli = inventory_cli
    missing = cli.cwd / "missing-history.jsonl"
    succeeded(cli.run("--bag", str(missing), "bags", "--resume"))
    assert not missing.exists() and not (cli.home / ".postbag").exists()
    seed(cli.default, claude(session_id=FIRST))
    selected = cli.cwd / "selected-history.jsonl"
    seed(selected, claude(session_id=SECOND))
    seed(cli.cwd / "unselected-history.jsonl", claude(session_id=THIRD))
    text = succeeded(cli.run("--bag", str(selected), "bags", "--resume"))
    assert sorted(COMMAND.findall(text)) == sorted([FIRST, SECOND])
    assert THIRD not in text


def inventory_view(cli, columns):
    """Run the public resume flag in a pipe or with the shared terminal wrapper."""
    if columns is None:
        return cli.run("bags", "--resume")
    environment = {**cli.environment, "POSTBAG_TEST_TTY": "1", "POSTBAG_TEST_NOW": NOW,
                   "COLUMNS": str(columns), "TZ": "UTC0", "NO_COLOR": ""}
    return subprocess.run(
        [sys.executable, "-c", WRAPPER, str(SCRIPT), "bags", "--resume"],
        cwd=cli.cwd, env=environment, capture_output=True, text=True, timeout=3,
    )


@pytest.mark.parametrize("columns", [None, 40, 120], ids=["pipe", "narrow", "wide"])
def test_missing_resume_ids_are_explained_once_without_repeating_peers(inventory_cli, columns):
    cli = inventory_cli
    seed(cli.default, opened(4), claude("ada", None, door="first"),
         claude("cleo", None, door="second"))
    seed(cli.named / "review.jsonl", claude("dora", None, door="third"))
    text = plain(succeeded(inventory_view(cli, columns)))
    unwrapped = " ".join(text.split())
    assert not COMMAND.search(text)
    assert "No Claude session IDs recorded yet." in unwrapped
    assert unwrapped.count("rejoin") == 1
    assert "Unknown" not in text
    assert "conversation at join" not in text
    for peer in ("ada", "cleo", "dora"):
        assert text.count("@" + peer) == 1
    if columns == 120:
        assert re.search(r"Bag\s+Letters left\s+Last letter\s+Registered peers", text)
    elif columns == 40:
        assert "Last letter:" in text


@pytest.mark.parametrize("columns", [None, 40, 120], ids=["pipe", "narrow", "wide"])
def test_partial_resume_ids_add_only_copyable_commands_and_one_missing_count(inventory_cli, columns):
    cli = inventory_cli
    seed(cli.default, opened(4), claude("ada", FIRST, door="first"),
         claude("cleo", None, door="second"), joined("bob"))
    seed(cli.named / "review.jsonl", claude("dora", SECOND, door="third"),
         claude("eve", None, door="fourth"))
    text = plain(succeeded(inventory_view(cli, columns)))
    unwrapped = " ".join(text.split())
    assert sorted(COMMAND.findall(text)) == sorted([FIRST, SECOND])
    command_lines = [line.strip() for line in text.splitlines() if COMMAND.search(line)]
    assert command_lines == [f"@ada → claude --resume {FIRST}", f"@dora → claude --resume {SECOND}"]
    assert "2 Claude peers have no session ID recorded." in unwrapped
    assert unwrapped.count("no session ID recorded") == 1
    assert "saved history" in unwrapped and "join" in unwrapped
    assert "Unknown" not in text
    for peer in ("cleo", "eve", "bob"):
        assert text.count("@" + peer) == 1
    if columns == 120:
        assert re.search(r"Bag\s+Letters left\s+Last letter\s+Registered peers", text)
    lines = text.splitlines()
    default_row = next(i for i, line in enumerate(lines) if re.match(r"^default(?:\s|$)", line))
    review_row = next(i for i, line in enumerate(lines) if re.match(r"^review(?:\s|$)", line))
    assert default_row < next(i for i, line in enumerate(lines) if FIRST in line) < review_row
    assert review_row < next(i for i, line in enumerate(lines) if SECOND in line)


@pytest.mark.parametrize("columns", [None, 40, 120], ids=["pipe", "narrow", "wide"])
@pytest.mark.parametrize("kind", ["empty", "codex-only"])
def test_resume_without_claude_peers_has_no_misleading_rejoin_note(inventory_cli, columns, kind):
    cli = inventory_cli
    if kind == "codex-only":
        seed(cli.default, opened(3), joined("bob"))
    text = plain(succeeded(inventory_view(cli, columns)))
    unwrapped = " ".join(text.lower().split())
    assert not COMMAND.search(text)
    assert "session id" not in unwrapped
    assert "rejoin" not in unwrapped
    assert "saved history" not in unwrapped
    if kind == "empty":
        assert not (cli.home / ".postbag").exists()


def test_resume_missing_count_excludes_unavailable_bags(inventory_cli):
    cli = inventory_cli
    seed(cli.default, claude("ada", FIRST, door="first"), claude("cleo", None, door="second"))
    unavailable = cli.named / "broken.jsonl"
    seed(unavailable, claude("dora", None, door="third"))
    with unavailable.open("a", encoding="utf-8") as ledger:
        ledger.write("not-json\n")
    before = fingerprint(unavailable)
    result = inventory_view(cli, 120)
    assert result.returncode == 1
    assert "in bag broken" in result.stderr
    text = plain(result.stdout)
    assert "1 Claude peer has no session ID recorded." in text
    assert "Inventory incomplete" in text
    assert "@dora" not in text
    assert fingerprint(unavailable) == before
