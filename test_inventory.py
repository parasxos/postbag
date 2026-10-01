"""Read-only bag inventory through the public CLI, with wholly private state."""

import errno
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().with_name("postbag.py")
PRIVATE_BODY = "INVENTORY-PRIVATE-LETTER-BODY"
PRIVATE_SOCKET = "/tmp/inventory-private-never-used.sock"
PRIVATE_TOKEN = "inventory-private-fake-token"
PRIVATE_THREAD = "inventory-private-fake-thread"


@pytest.fixture
def inventory_cli(tmp_path):
    home, cwd = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    cwd.mkdir()
    called = tmp_path / "transport-called"
    executable = tmp_path / "fake-codex"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import os\n"
        "from pathlib import Path\n"
        "Path(os.environ['POSTBAG_TEST_NATIVE_CALLED']).write_text('unexpected transport')\n"
        "raise SystemExit(97)\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    base = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("CLAUDE_", "CODEX_", "POSTBAG_"))
    }
    base.update(
        HOME=str(home), POSTBAG_CODEX=str(executable), POSTBAG_TEST_NATIVE_CALLED=str(called),
        CODEX_SESSION_ID=PRIVATE_THREAD,
        CLAUDE_CODE_MESSAGING_SOCKET=PRIVATE_SOCKET,
        CLAUDE_CODE_MESSAGING_TOKEN=PRIVATE_TOKEN,
    )

    def run(*args, extra=None, **kwargs):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], cwd=cwd,
            env={**base, **(extra or {})}, capture_output=True, text=True, timeout=3,
            **kwargs,
        )

    result = SimpleNamespace(
        run=run, home=home, cwd=cwd, environment=base, called=called,
        default=home / ".postbag" / "ledger.jsonl",
        named=home / ".postbag" / "bags",
    )
    yield result
    assert not called.exists(), "bags must not call a native transport"


def joined(peer, vendor="codex", door=PRIVATE_THREAD, *, legacy=False):
    result = {"kind": "join", "peer": peer}
    if not legacy:
        result["vendor"] = vendor
    result.update({"thread": door} if vendor == "codex" else {
        "socket": PRIVATE_SOCKET, "token": door,
    })
    return result


def opened(limit):
    return {"kind": "open", "limit": limit}


def letter(**extra):
    return {"kind": "letter", "from": "ada", "to": "bob", "body": PRIVATE_BODY, **extra}


def seed(path, *records):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [dict(n=number, at=f"2026-09-19T10:00:{number:02d}+02:00", **record)
            for number, record in enumerate(records, 1)]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    path.chmod(0o600)  # as postbag creates it. Tests that want an exposed ledger re-mode it themselves
    return rows


def fingerprint(path):
    metadata = path.stat()
    return path.read_bytes(), stat.S_IMODE(metadata.st_mode), metadata.st_mtime_ns


def table(output):
    """Ignore padding; these fixtures deliberately use no vertical bars in paths."""
    lines = output.splitlines()
    header = next(i for i, line in enumerate(lines)
                  if [cell.strip() for cell in line.split("|")] ==
                  ["Bag", "Letters", "Last letter", "Registered peers"])
    rows = {}
    for line in lines[header + 1:]:
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) != 4 or not cells[0] or set("".join(cells)) <= {"-", ":", "+"}:
            continue
        assert cells[0] not in rows, f"duplicate inventory row: {cells[0]}"
        rows[cells[0]] = dict(zip(("letters", "last", "peers"), cells[1:]))
    return rows


def counts(output, *, total, letters, empty, unavailable):
    # The prose and punctuation may change. The four factual counts may not, and zero counts are omitted.
    summary = output.splitlines()[0]
    assert re.search(rf"\b{total}\s+bags?\b", summary, re.I), output
    for amount, label in ((letters, r"with letters\b"), (empty, r"empty\b"), (unavailable, r"unavailable\b")):
        if amount:
            assert re.search(rf"\b{amount}\s+{label}", summary, re.I), output
        else:
            assert not re.search(rf"\d+\s+{label}", summary, re.I), output


def success(result):
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "Traceback" not in result.stdout
    return table(result.stdout)


def sanitized_failure(result):
    assert result.returncode == 1
    assert result.stderr.rstrip().endswith("; stop and ask the human")
    assert "Traceback" not in result.stderr
    assert all(secret not in result.stdout + result.stderr for secret in (
        PRIVATE_BODY, PRIVATE_SOCKET, PRIVATE_TOKEN, PRIVATE_THREAD,
    ))
    return table(result.stdout)


@pytest.mark.parametrize("selection", ["bare", "named", "custom"])
def test_empty_inventory_does_not_create_home_state_or_selected_path(inventory_cli, selection):
    cli = inventory_cli
    missing = cli.cwd / "missing" / "selected.jsonl"
    args = (["--bag", "missing"] if selection == "named" else
            ["--bag", str(missing)] if selection == "custom" else [])
    result = cli.run(*args, "bags")
    assert success(result) == {}
    counts(result.stdout, total=0, letters=0, empty=0, unavailable=0)
    assert not (cli.home / ".postbag").exists()
    assert not list(cli.cwd.iterdir())


def test_inventory_discovers_only_default_and_valid_direct_named_files(inventory_cli):
    cli = inventory_cli
    seed(cli.default, opened(3))
    seed(cli.named / "review.jsonl", opened(4))
    seed(cli.named / ("a" * 16 + ".jsonl"), opened(5))
    seed(cli.named / "edge-.jsonl", opened(6))
    for filename in ("default.jsonl", "Invalid.jsonl", "_hidden.jsonl", "a" * 17 + ".jsonl",
                     "review.txt", "review.jsonl.bak", ".hidden.jsonl"):
        seed(cli.named / filename, opened(7))
    seed(cli.named / "nested" / "inner.jsonl", opened(8))
    result = cli.run("bags")
    rows = success(result)
    assert set(rows) == {"default", "review", "a" * 16, "edge-"}
    counts(result.stdout, total=4, letters=0, empty=4, unavailable=0)


def test_summary_counts_letters_and_tolerates_legacy_opens_and_overruns(inventory_cli):
    cli = inventory_cli
    seed(cli.default, opened(3), letter())
    seed(cli.named / "empty.jsonl")
    seed(cli.named / "spent.jsonl", opened(1), letter())
    seed(cli.named / "overrun.jsonl", opened(1), letter(), letter())
    before = seed(cli.named / "unopened.jsonl", letter())
    reopened = seed(cli.named / "reopened.jsonl", opened(1), letter(), opened(7))
    result = cli.run("bags")
    rows = success(result)
    counts(result.stdout, total=6, letters=5, empty=1, unavailable=0)
    assert {label: row["letters"] for label, row in rows.items()} == {
        "default": "1", "empty": "0", "spent": "1", "overrun": "2", "unopened": "1", "reopened": "1",
    }
    assert rows["empty"]["last"] == "-"
    assert rows["unopened"]["last"] == before[-1]["at"]
    assert rows["reopened"]["last"] == reopened[1]["at"]
    assert "exchange" not in result.stdout and "budget" not in result.stdout.lower()


def test_last_letter_and_current_peers_use_full_legacy_replay_without_disclosing_contents(inventory_cli):
    cli = inventory_cli
    records = seed(
        cli.default,
        joined("claude", "claude", PRIVATE_TOKEN, legacy=True),
        joined("codex", legacy=True),
        opened(5),
        letter(**{"from": "claude", "to": "codex"}),
        joined("ada", "claude", PRIVATE_TOKEN),       # rename claude's first door
        joined("codex", door="fake-replacement"),    # take codex's old name
        joined("bob", door="fake-replacement"),      # release codex; old door stays displaced
        joined("ada", "claude", "fake-other-token"),
        joined("cleo", "claude", "fake-other-token"),
    )
    cli.default.chmod(0o644)
    before = fingerprint(cli.default)
    result = cli.run("bags")
    rows = success(result)
    assert rows["default"]["last"] == records[3]["at"]
    assert rows["default"]["peers"] == "@bob (codex), @cleo (claude)"
    assert rows["default"]["letters"] == "1"
    assert all(secret not in result.stdout + result.stderr for secret in (
        PRIVATE_BODY, PRIVATE_SOCKET, PRIVATE_TOKEN, PRIVATE_THREAD,
        "fake-replacement", "fake-other-token",
    ))
    assert fingerprint(cli.default) == before


@pytest.mark.parametrize("selector", ["environment", "flag"])
def test_selected_custom_path_is_included_without_searching_for_other_custom_ledgers(inventory_cli, selector):
    cli = inventory_cli
    selected = cli.cwd / "custom bag's history.log"
    unrelated = cli.cwd / "undiscovered.jsonl"
    seed(cli.default, opened(2))
    seed(selected, opened(3))
    seed(unrelated, opened(4))
    before = {path: fingerprint(path) for path in (cli.default, selected, unrelated)}
    args = ["--bag", str(selected)] if selector == "flag" else []
    extra = {"POSTBAG_LEDGER": str(unrelated if selector == "flag" else selected)}
    result = cli.run(*args, "bags", extra=extra)
    assert set(success(result)) == {"default", str(selected)}
    counts(result.stdout, total=2, letters=0, empty=2, unavailable=0)
    assert {path: fingerprint(path) for path in before} == before


@pytest.mark.parametrize("canonical", ["default", "review"])
@pytest.mark.parametrize("selector", ["environment", "flag"])
def test_selected_standard_path_is_deduplicated_under_its_canonical_label(inventory_cli, canonical, selector):
    cli = inventory_cli
    path = cli.default if canonical == "default" else cli.named / "review.jsonl"
    seed(path, opened(2))
    args = ["--bag", str(path)] if selector == "flag" else []
    result = cli.run(*args, "bags", extra={"POSTBAG_LEDGER": str(path)})
    assert set(success(result)) == {canonical}
    counts(result.stdout, total=1, letters=0, empty=1, unavailable=0)


@pytest.mark.parametrize("canonical", ["default", "review"])
@pytest.mark.parametrize("selector", ["environment", "flag"])
def test_parent_directory_alias_of_a_standard_file_is_deduplicated(inventory_cli, canonical, selector):
    cli = inventory_cli
    path = cli.default if canonical == "default" else cli.named / "review.jsonl"
    seed(path, opened(2))
    alias = path.parent / ".." / path.parent.name / path.name
    args = ["--bag", str(alias)] if selector == "flag" else []
    result = cli.run(*args, "bags", extra={"POSTBAG_LEDGER": str(alias)})
    assert set(success(result)) == {canonical}
    counts(result.stdout, total=1, letters=0, empty=1, unavailable=0)


def test_symlink_then_parent_directory_keeps_distinct_underlying_files(inventory_cli):
    cli = inventory_cli
    standard = cli.named / "review.jsonl"
    seed(standard, opened(2), letter(), letter())
    other = cli.cwd / "elsewhere" / "review.jsonl"
    seed(other, *(letter() for _ in range(7)))
    child = other.parent / "child"
    child.mkdir()
    (cli.named / "link").symlink_to(child, target_is_directory=True)
    alias = cli.named / "link" / ".." / "review.jsonl"
    before = {path: fingerprint(path) for path in (standard, other)}
    result = cli.run("--bag", str(alias), "bags")
    rows = success(result)
    assert set(rows) == {"review", str(alias)}
    assert rows["review"]["letters"] == "2"
    assert rows[str(alias)]["letters"] == "7"
    counts(result.stdout, total=2, letters=2, empty=0, unavailable=0)
    assert {path: fingerprint(path) for path in before} == before


def test_selected_final_symlink_is_unavailable_instead_of_deduplicated_with_its_target(inventory_cli):
    cli = inventory_cli
    standard = cli.named / "review.jsonl"
    seed(standard, opened(2))
    alias = cli.cwd / "selected-link.jsonl"
    alias.symlink_to(standard)
    before = fingerprint(standard)
    result = cli.run("--bag", str(alias), "bags")
    rows = sanitized_failure(result)
    assert set(rows) == {"review", str(alias)}
    assert rows[str(alias)]["letters"].lower() == "unavailable"
    counts(result.stdout, total=2, letters=0, empty=1, unavailable=1)
    assert alias.is_symlink() and fingerprint(standard) == before


def test_last_letter_timestamp_is_canonical_and_cannot_emit_an_escape_character(inventory_cli):
    cli = inventory_cli
    records = seed(cli.default, opened(2), letter(), opened(7))
    # datetime.fromisoformat accepts any one-character date/time separator.
    records[1]["at"] = "2026-09-19\x1b10:00:02+02:00"
    cli.default.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
    before = fingerprint(cli.default)
    result = cli.run("bags")
    rows = success(result)
    assert rows["default"]["last"] == "2026-09-19T10:00:02+02:00"
    assert "\x1b" not in result.stdout + result.stderr
    assert rows["default"]["last"] != records[-1]["at"]
    assert fingerprint(cli.default) == before


def test_missing_selected_custom_path_does_not_hide_standard_bags(inventory_cli):
    cli = inventory_cli
    seed(cli.default, opened(2))
    missing = cli.cwd / "missing" / "custom.jsonl"
    result = cli.run("bags", extra={"POSTBAG_LEDGER": str(missing)})
    assert set(success(result)) == {"default"}
    assert not missing.parent.exists()


@pytest.mark.parametrize("damage", ["json", "shape", "utf8", "truncated"])
def test_bad_ledger_is_an_unavailable_row_while_other_bags_remain_visible(inventory_cli, damage):
    cli = inventory_cli
    seed(cli.default, opened(2))
    broken = cli.named / "broken.jsonl"
    seed(broken)
    payload = {
        "json": ('{"token":"' + PRIVATE_TOKEN + '","body":"' + PRIVATE_BODY + '",\n').encode(),
        "shape": (json.dumps({"token": PRIVATE_TOKEN, "body": PRIVATE_BODY}) + "\n").encode(),
        "utf8": b'\xff\n',
        "truncated": json.dumps({"n": 1, "at": "2026-09-19T10:00:01+02:00",
                                  "kind": "open", "limit": 2}).encode(),
    }[damage]
    broken.write_bytes(payload)
    broken.chmod(0o644)
    before = fingerprint(broken)
    result = cli.run("bags")
    rows = sanitized_failure(result)
    assert set(rows) == {"default", "broken"}
    assert rows["broken"]["letters"].lower() == "unavailable"
    assert "broken" in result.stderr
    counts(result.stdout, total=2, letters=0, empty=1, unavailable=1)
    assert fingerprint(broken) == before


@pytest.mark.parametrize("kind", ["symlink", "dangling-symlink", "fifo", "directory"])
def test_nonregular_candidate_is_reported_without_following_or_blocking(inventory_cli, kind):
    cli = inventory_cli
    seed(cli.default, opened(2))
    cli.named.mkdir()
    path = cli.named / "unsafe.jsonl"
    target = cli.cwd / "outside.jsonl"
    if kind == "symlink":
        seed(target, opened(4))
        before = fingerprint(target)
        path.symlink_to(target)
    elif kind == "dangling-symlink":
        path.symlink_to(target)
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        path.mkdir()
    mode = path.lstat().st_mode
    result = cli.run("bags")
    rows = sanitized_failure(result)
    assert set(rows) == {"default", "unsafe"}
    assert rows["unsafe"]["letters"].lower() == "unavailable"
    counts(result.stdout, total=2, letters=0, empty=1, unavailable=1)
    assert path.lstat().st_mode == mode
    if kind == "symlink":
        assert fingerprint(target) == before
    elif kind == "dangling-symlink":
        assert not target.exists()


def test_exclusively_locked_bag_is_unavailable_without_delaying_other_rows(inventory_cli):
    cli = inventory_cli
    seed(cli.default, opened(2))
    locked = cli.named / "locked.jsonl"
    seed(locked, opened(3))
    before = fingerprint(locked)
    with locked.open("rb") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        result = cli.run("bags")  # Fixture timeout catches a blocking LOCK_SH.
    rows = sanitized_failure(result)
    assert set(rows) == {"default", "locked"}
    assert rows["locked"]["letters"].lower() == "unavailable"
    assert re.search(r"busy|lock", result.stderr, re.I)
    counts(result.stdout, total=2, letters=0, empty=1, unavailable=1)
    assert fingerprint(locked) == before


@pytest.mark.parametrize("error_number", [errno.ENOENT, errno.EACCES], ids=["disappeared-during-scan", "denied-during-scan"])
def test_scan_iteration_failure_preserves_discovered_rows_and_reports_incomplete_inventory(
    inventory_cli, error_number,
):
    cli = inventory_cli
    seed(cli.default, opened(2))
    named = cli.named / "review.jsonl"
    seed(named, opened(3))
    before = {path: fingerprint(path) for path in (cli.default, named)}
    # Inject only the otherwise difficult OS race: opening the iterator succeeds,
    # one real directory entry is delivered, and its next read fails.
    program = """
import importlib.util
import os
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location('postbag_fault_review', sys.argv[1])
postbag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(postbag)
original_scandir = os.scandir

class InterruptedScan:
    def __init__(self, entries):
        self.entries = entries
        self.delivered = False
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        self.entries.close()
    def __iter__(self):
        return self
    def __next__(self):
        if not self.delivered:
            self.delivered = True
            return next(self.entries)
        number = int(sys.argv[3])
        raise OSError(number, os.strerror(number))

def interrupted_scandir(path):
    entries = original_scandir(path)
    return InterruptedScan(entries) if Path(path) == Path(sys.argv[2]) else entries

os.scandir = interrupted_scandir
postbag.main(['bags'])
"""
    result = subprocess.run(
        [sys.executable, "-c", program, str(SCRIPT), str(cli.named), str(error_number)],
        cwd=cli.cwd, env=cli.environment, capture_output=True, text=True, timeout=3,
    )
    rows = sanitized_failure(result)
    assert set(rows) == {"default", "review"}
    counts(result.stdout, total=2, letters=0, empty=2, unavailable=0)
    assert "incomplete" in result.stdout.lower()
    assert str(cli.named) in result.stderr
    assert {path: fingerprint(path) for path in before} == before


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file read permissions")
def test_unreadable_ledger_remains_unavailable_without_changing_its_permissions(inventory_cli):
    cli = inventory_cli
    seed(cli.default, opened(2))
    unreadable = cli.named / "private.jsonl"
    seed(unreadable, opened(3))
    before = unreadable.read_bytes()
    unreadable.chmod(0)
    try:
        result = cli.run("bags")
        rows = sanitized_failure(result)
        assert set(rows) == {"default", "private"}
        assert rows["private"]["letters"].lower() == "unavailable"
        counts(result.stdout, total=2, letters=0, empty=1, unavailable=1)
        assert stat.S_IMODE(unreadable.stat().st_mode) == 0
    finally:
        unreadable.chmod(0o600)
    assert unreadable.read_bytes() == before


def test_inventory_explains_scan_scope_without_claiming_peer_presence(inventory_cli):
    cli = inventory_cli
    seed(cli.default, joined("ada"), opened(2))
    result = cli.run("bags")
    success(result)
    assert ".postbag" in result.stdout and "bags" in result.stdout
    assert "custom" in result.stdout.lower() and "select" in result.stdout.lower()
    assert not re.search(r"\b(?:active|alive|online|offline|live|liveness|presence)\b", result.stdout, re.I)


@pytest.mark.parametrize("control", ["\n", "\t", "\x85", "\u2028"])
def test_inventory_keeps_path_validation_and_valid_flag_precedence(inventory_cli, control):
    cli = inventory_cli
    invalid = str(cli.cwd / ("bad" + control) / "history.jsonl")
    failed = cli.run("--bag", invalid, "bags")
    assert failed.returncode == 1
    assert "printable" in failed.stderr and "Traceback" not in failed.stderr
    assert failed.stderr.rstrip().endswith("; stop and ask the human")
    assert failed.stdout == "" and not list(cli.cwd.iterdir())
    result = cli.run("--bag", "default", "bags", extra={"POSTBAG_LEDGER": invalid})
    assert success(result) == {}
    assert not (cli.home / ".postbag").exists()


@pytest.mark.parametrize("with_error", [False, True])
def test_inventory_exits_quietly_when_its_output_pipe_is_closed(inventory_cli, with_error):
    cli = inventory_cli
    seed(cli.default, opened(2))
    if with_error:
        broken = cli.named / "broken.jsonl"
        seed(broken)
        broken.write_bytes(b"not json\n")
    before = fingerprint(cli.default)
    reader, writer = os.pipe()
    os.close(reader)
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "bags"], cwd=cli.cwd, env=cli.environment,
            stdout=writer, stderr=subprocess.PIPE, text=True, timeout=3,
        )
    finally:
        os.close(writer)
    assert result.returncode == 0 and result.stderr == ""
    assert fingerprint(cli.default) == before
    if with_error:
        assert broken.read_bytes() == b"not json\n"
