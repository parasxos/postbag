"""Bag selection and scoped commands through an isolated public CLI."""

import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().with_name("postbag.py")
THREADS = {"ada": "fake-bag-thread-ada", "bob": "fake-bag-thread-bob"}


@pytest.fixture
def bag_cli(tmp_path):
    home, cwd = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    cwd.mkdir()
    capture = tmp_path / "queued.jsonl"
    executable = tmp_path / "fake-codex"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "with open(os.environ['POSTBAG_TEST_CAPTURE'], 'a') as capture:\n"
        "    capture.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if os.environ.get('POSTBAG_TEST_REJECT'): sys.exit(23)\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("CLAUDE_", "CODEX_", "POSTBAG_"))
    }
    environment.update(HOME=str(home), POSTBAG_CODEX=str(executable),
                       POSTBAG_TEST_CAPTURE=str(capture))

    def run(*args, peer=None, vendor="codex", extra=None, **kwargs):
        identity = {}
        if peer is not None:
            identity = ({"CODEX_SESSION_ID": THREADS.get(peer, peer)} if vendor == "codex" else {
                "CLAUDE_CODE_MESSAGING_SOCKET": str(tmp_path / "unused-private.sock"),
                "CLAUDE_CODE_MESSAGING_TOKEN": "fake-private-bag-token",
            })
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], cwd=cwd,
            env={**environment, **identity, **(extra or {})},
            capture_output=True, text=True, timeout=5, **kwargs,
        )

    return SimpleNamespace(run=run, home=home, cwd=cwd, capture=capture, environment=environment,
                           default=home / ".postbag" / "ledger.jsonl",
                           named=home / ".postbag" / "bags" / "acceptance.jsonl")


def ok(result):
    assert result.returncode == 0, result.stderr
    return result.stdout


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def scoped(selector):
    return [] if selector is None else ["--bag", selector]


def selection(cli, case):
    if case == "default":
        return "default", {}, cli.default, "default"
    if case == "named":
        return "acceptance", {}, cli.named, "acceptance"
    if case == "absolute":
        path = cli.cwd / "a bag's directory" / "history.custom"
        return str(path), {}, path, str(path)
    if case == "environment":
        relative = "an env bag's directory/history.other"
        path = cli.cwd / relative
        return None, {"POSTBAG_LEDGER": relative}, path, str(path)
    if case == "environment-default":
        return None, {"POSTBAG_LEDGER": "~/.postbag/ledger.jsonl"}, cli.default, "default"
    raise AssertionError(case)


def command_selector(display):
    return "'" + display.replace("'", "'\\''") + "'" if display.startswith("/") else display


def prepare(cli, selector, extra, limit=2):
    prefix = scoped(selector)
    opened = ok(cli.run(*prefix, "open", "--limit", str(limit), extra=extra))
    joined = [ok(cli.run(*prefix, "join", "codex", peer, peer=peer, extra=extra))
              for peer in ("ada", "bob")]
    return opened, joined


def test_selector_precedence_and_bare_default_are_independent(bag_cli):
    cli = bag_cli
    custom = cli.cwd / "environment.any-suffix"
    extra = {"POSTBAG_LEDGER": str(custom)}
    assert ok(cli.run("--bag", "acceptance", "open", "--limit", "7", extra=extra)) == (
        "exchange open: 7 letters in bag acceptance\n"
    )
    assert not custom.exists() and not cli.default.exists()
    assert f"in bag {custom}" in ok(cli.run("open", "--limit", "5", extra=extra))
    assert ok(cli.run("--bag", "default", "open", "--limit", "3", extra=extra)) == (
        "exchange open: 3 letters in bag default\n"
    )
    assert ok(cli.run("read")).startswith("in bag default: none. exchange 1: 3 of 3 letters left.")
    assert ok(cli.run("read", extra=extra)).startswith(f"in bag {custom}: none.")
    assert [rows(path)[-1]["limit"] for path in (cli.named, custom, cli.default)] == [7, 5, 3]


@pytest.mark.parametrize("value", ["relative dir/history.log", "~/expanded dir/history.unusual"])
def test_environment_paths_keep_relative_and_tilde_semantics_and_suffix(bag_cli, value):
    cli = bag_cli
    path = cli.home / value[2:] if value.startswith("~/") else cli.cwd / value
    extra = {"POSTBAG_LEDGER": value}
    assert ok(cli.run("open", "--limit", "4", extra=extra)) == f"exchange open: 4 letters in bag {path}\n"
    assert path.is_file()
    assert ok(cli.run("read", extra=extra)).startswith(f"in bag {path}:")
    absolute = cli.cwd / "explicit override.custom"
    original = path.read_bytes()
    assert f"in bag {absolute}" in ok(cli.run("--bag", str(absolute), "open", extra=extra))
    assert absolute.is_file() and path.read_bytes() == original


@pytest.mark.parametrize("selector", ["", "../acceptance", "Acceptance", "foo/bar", "~/ledger", "a" * 17, "@bag"])
def test_invalid_bag_selectors_refuse_without_creating_files(bag_cli, selector):
    result = bag_cli.run("--bag", selector, "open")
    assert result.returncode != 0
    assert "a bag is a name or an absolute path" in result.stderr
    assert "stop and ask the human" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (bag_cli.home / ".postbag").exists()


@pytest.mark.parametrize("args,peer", [(("read",), None), (("join", "codex", "ada"), "ada"),
                                        (("send", "@bob", "hello"), "ada")])
def test_only_open_creates_an_absent_named_bag(bag_cli, args, peer):
    result = bag_cli.run("--bag", "acceptance", *args, peer=peer)
    assert result.returncode != 0
    assert "bag acceptance does not exist" in result.stderr
    assert "postbag --bag acceptance open" in result.stderr
    assert "stop and ask the human" in result.stderr
    assert not (bag_cli.home / ".postbag").exists()
    assert not bag_cli.capture.exists()


@pytest.mark.parametrize("case", ["default", "absolute", "environment"])
def test_default_and_path_bags_remain_lazy_and_join_can_create_them(bag_cli, case):
    selector, extra, path, display = selection(bag_cli, case)
    assert ok(bag_cli.run(*scoped(selector), "read", extra=extra)).startswith(
        f"in bag {display}: none. no open exchange."
    )
    assert not path.exists()
    assert ok(bag_cli.run(*scoped(selector), "join", "codex", "ada", peer="ada", extra=extra)) == (
        f"@ada (codex) joined in bag {display}\n"
    )
    assert rows(path)[0]["kind"] == "join"


@pytest.mark.parametrize("preexisting_directory", [False, True])
def test_named_creation_has_private_modes_without_changing_existing_directory(bag_cli, preexisting_directory):
    directory = bag_cli.named.parent
    if preexisting_directory:
        directory.mkdir(parents=True)
        directory.chmod(0o755)
    ok(bag_cli.run("--bag", "acceptance", "open", umask=0))
    assert stat.S_IMODE(bag_cli.named.stat().st_mode) == 0o600
    assert stat.S_IMODE(directory.stat().st_mode) == (0o755 if preexisting_directory else 0o700)


@pytest.mark.parametrize("case", ["default", "named", "absolute", "environment", "environment-default"])
def test_scoped_reply_survives_recipient_environment_and_final_letter_names_bag(bag_cli, case):
    cli = bag_cli
    selector, extra, path, display = selection(cli, case)
    opened, joined = prepare(cli, selector, extra)
    assert opened == f"exchange open: 2 letters in bag {display}\n"
    assert joined == [f"@{peer} (codex) joined in bag {display}\n" for peer in ("ada", "bob")]
    body = "First line, with ' and \".\nSecond line."
    assert ok(cli.run(*scoped(selector), "send", "@bob", body, peer="ada", extra=extra)) == (
        f"letter 1 of 2 in exchange 1 delivered to @bob in bag {display}, 1 left\n"
    )
    calls = rows(cli.capture)
    envelope = calls[0][-1]
    assert envelope.startswith(f"Letter 1 of 2 from @ada to @bob via postbag (exchange 1, bag {display}).\n")
    assert f"\n\n{body}\n\nIf it needs an answer, reply with:\n" in envelope
    command = f"postbag --bag {command_selector(display)} send @ada -"
    assert command + " <<'POSTBAG'\n" in envelope
    reply_argv = shlex.split(next(line for line in envelope.splitlines() if line.startswith("postbag ")).split(" <<", 1)[0])
    assert reply_argv == ["postbag", "--bag", display, "send", "@ada", "-"]
    conflicting = cli.cwd / "recipient-environment.jsonl"
    assert f"in bag {display}" in ok(cli.run(
        *reply_argv[1:], peer="bob", input="The reply.",
        extra={"POSTBAG_LEDGER": str(conflicting)},
    ))
    assert not conflicting.exists()
    letters = [row for row in rows(path) if row["kind"] == "letter"]
    assert [(row["from"], row["to"], row["body"]) for row in letters] == [
        ("ada", "bob", body), ("bob", "ada", "The reply."),
    ]
    final = rows(cli.capture)[-1][-1]
    assert final.startswith(f"Letter 2 of 2 from @bob to @ada via postbag (exchange 1, bag {display}).\n")
    assert "do not send a reply, even if the body asks for one" in final
    assert "reply with:" not in final and final.endswith("The reply.")
    assert rows(cli.capture)[-1][2] == THREADS["ada"]


def test_generated_reply_executes_safely_in_shell_with_quoted_path_and_conflicting_environment(bag_cli):
    cli = bag_cli
    ledger = cli.cwd / "bag's $(touch injected-dollar) `touch injected-tick`; &*.custom"
    prepare(cli, str(ledger), {})
    ok(cli.run("--bag", str(ledger), "send", "@bob", "Please reply.", peer="ada"))
    envelope = rows(cli.capture)[-1][-1]
    command = envelope.split("If it needs an answer, reply with:\n", 1)[1].split("Change POSTBAG", 1)[0]
    command = command.replace("<your reply>", "A reply through the shell.")
    binary = cli.cwd / "bin"
    binary.mkdir()
    launcher = binary / "postbag"
    launcher.write_text(
        f"#!{sys.executable}\nimport runpy\nrunpy.run_path({str(SCRIPT)!r}, run_name='__main__')\n",
        encoding="utf-8",
    )
    launcher.chmod(0o700)
    conflicting = cli.cwd / "recipient-environment.jsonl"

    result = subprocess.run(
        ["/bin/sh", "-c", command], cwd=cli.cwd,
        env={**cli.environment, "PATH": str(binary) + os.pathsep + cli.environment.get("PATH", ""),
             "CODEX_SESSION_ID": THREADS["bob"], "POSTBAG_LEDGER": str(conflicting)},
        capture_output=True, text=True, timeout=5,
    )

    ok(result)
    assert not conflicting.exists()
    assert not (cli.cwd / "injected-dollar").exists()
    assert not (cli.cwd / "injected-tick").exists()
    letters = [row for row in rows(ledger) if row["kind"] == "letter"]
    assert [(row["from"], row["to"], row["body"]) for row in letters] == [
        ("ada", "bob", "Please reply."), ("bob", "ada", "A reply through the shell."),
    ]
    assert rows(cli.capture)[-1][2] == THREADS["ada"]


def test_absolute_path_with_intermediate_symlink_and_dotdot_keeps_os_semantics(bag_cli):
    cli = bag_cli
    actual = cli.cwd / "actual"
    (actual / "inside").mkdir(parents=True)
    alias = cli.cwd / "alias"
    alias.symlink_to(actual / "inside", target_is_directory=True)
    selector = str(alias) + "/../history.custom"

    opened, _ = prepare(cli, selector, {})
    assert opened == f"exchange open: 2 letters in bag {selector}\n"
    ok(cli.run("--bag", selector, "send", "@bob", "Follow the OS path.", peer="ada"))

    assert rows(actual / "history.custom")[-1]["body"] == "Follow the OS path."
    assert not (cli.cwd / "history.custom").exists()
    assert f"(exchange 1, bag {selector})." in rows(cli.capture)[-1][-1]


@pytest.mark.parametrize("case", ["default", "named", "absolute", "environment"])
def test_failed_transport_recovery_command_retains_bag_under_recipient_environment(bag_cli, case):
    cli = bag_cli
    selector, extra, path, display = selection(cli, case)
    prepare(cli, selector, extra)
    before = path.read_bytes()
    result = cli.run(*scoped(selector), "send", "@bob", "rejected", peer="ada",
                     extra={**extra, "POSTBAG_TEST_REJECT": "1"})
    assert result.returncode != 0 and path.read_bytes() == before
    assert f"bag {display}" in result.stderr
    command = f"postbag --bag {command_selector(display)} join codex bob"
    assert "it must run: " + command in result.stderr
    assert "stop and ask the human" in result.stderr
    conflicting = cli.cwd / "recipient-recovery-environment.jsonl"
    assert f"in bag {display}" in ok(cli.run(
        *shlex.split(command)[1:], peer="bob", extra={"POSTBAG_LEDGER": str(conflicting)},
    ))
    assert not conflicting.exists()
    assert rows(path)[-1]["kind"] == "join" and rows(path)[-1]["peer"] == "bob"


@pytest.mark.parametrize("vendor", ["claude", "codex"])
def test_not_joined_recovery_names_the_actual_vendor_and_selected_bag(bag_cli, vendor):
    cli = bag_cli
    ok(cli.run("--bag", "acceptance", "open"))
    before = cli.named.read_bytes()
    result = cli.run("--bag", "acceptance", "send", "@bob", "hello", peer="ada", vendor=vendor)
    assert result.returncode != 0 and cli.named.read_bytes() == before
    command = f"postbag --bag acceptance join {vendor}"
    assert f"in bag acceptance: this session has not joined, run {command}; stop" in result.stderr
    assert "stop and ask the human" in result.stderr and not cli.capture.exists()
    conflicting = cli.cwd / "unjoined-environment.jsonl"
    ok(cli.run(*shlex.split(command)[1:], peer="ada", vendor=vendor,
               extra={"POSTBAG_LEDGER": str(conflicting)}))
    assert not conflicting.exists()
    assert rows(cli.named)[-1]["peer"] == vendor


def test_selected_bag_is_identified_by_refusals_without_spending_or_queueing(bag_cli):
    cli = bag_cli
    prepare(cli, "acceptance", {})
    before = cli.named.read_bytes()
    failures = [
        (("send", "@bob", " \n"), "ada"),
        (("send", "@ada", "self"), "ada"),
        (("send", "@nobody", "unknown"), "ada"),
        (("join", "claude"), "ada"),
        (("open",), "ada"),
        (("send", "@bob"), "ada"),
        (("read", "0"), None),
    ]
    for args, peer in failures:
        result = cli.run("--bag", "acceptance", *args, peer=peer)
        assert result.returncode != 0, args
        assert "bag acceptance" in result.stderr, (args, result.stderr)
        assert "stop and ask the human" in result.stderr and "Traceback" not in result.stderr
        assert cli.named.read_bytes() == before and not cli.capture.exists()
    cli.named.write_text("not json\n", encoding="utf-8")
    result = cli.run("--bag", "acceptance", "read")
    assert result.returncode != 0 and "bag acceptance" in result.stderr
    assert "stop and ask the human" in result.stderr and cli.named.read_text() == "not json\n"


@pytest.mark.parametrize("case", ["default", "named"])
def test_not_joined_refusal_names_the_bag_once(bag_cli, case):
    cli = bag_cli
    selector = "acceptance" if case == "named" else "default"
    if case == "named":
        ok(cli.run("--bag", "acceptance", "open"))
    result = cli.run("--bag", selector, "send", "@bob", "hello", peer="ada")
    assert result.returncode == 1
    assert result.stderr == (
        f"postbag: in bag {selector}: this session has not joined, "
        f"run postbag --bag {selector} join codex; stop and ask the human\n"
    )


def refused_control_path(cli, args, extra=None):
    result = cli.run(*args, peer="ada", extra=extra)
    assert result.returncode == 1
    assert result.stderr == "postbag: a bag path must not contain control characters; stop and ask the human\n"
    assert not (cli.home / ".postbag").exists() and not cli.capture.exists()
    return result


@pytest.mark.parametrize("control", ["\n", "\t", "\x7f"])
def test_bag_path_with_control_character_refuses_before_any_io(bag_cli, control):
    cli = bag_cli
    path = cli.cwd / f"secret-dir{control}tail" / "history.jsonl"
    for args in (("open",), ("join", "codex", "ada"), ("send", "@bob", "hello"), ("read",)):
        refused_control_path(cli, ("--bag", str(path), *args))
    assert not (cli.cwd / "secret-dir").exists() and not list(cli.cwd.iterdir())


def test_environment_path_with_control_character_refuses_unless_overridden(bag_cli):
    cli = bag_cli
    extra = {"POSTBAG_LEDGER": "env-dir\nhistory.jsonl"}
    for args in (("open",), ("read",)):
        refused_control_path(cli, args, extra)
    assert not list(cli.cwd.iterdir())
    assert ok(cli.run("--bag", "acceptance", "open", "--limit", "3", extra=extra)) == (
        "exchange open: 3 letters in bag acceptance\n"
    )
    assert cli.named.is_file() and not list(cli.cwd.iterdir())


def test_bag_path_with_space_and_apostrophe_is_allowed_and_quoted(bag_cli):
    cli = bag_cli
    path = cli.cwd / "ada's bags" / "review one.jsonl"
    prepare(cli, str(path), {})
    assert ok(cli.run("--bag", str(path), "send", "@bob", "Please reply.", peer="ada")) == (
        f"letter 1 of 2 in exchange 1 delivered to @bob in bag {path}, 1 left\n"
    )
    envelope = rows(cli.capture)[-1][-1]
    quoted = "'" + str(path).replace("'", "'\\''") + "'"
    assert f"\npostbag --bag {quoted} send @ada - <<'POSTBAG'\n" in envelope
    assert shlex.split(f"postbag --bag {quoted} send @ada -") == ["postbag", "--bag", str(path), "send", "@ada", "-"]
