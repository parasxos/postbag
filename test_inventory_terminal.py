"""Terminal inventory behavior, using isolated subprocesses and fake local state."""

import json
import re
import subprocess
import sys
import unicodedata

import pytest

from test_inventory import (
    SCRIPT, fingerprint, inventory_cli, joined, letter, opened, seed, table,
)


SGR = re.compile(r"\x1b\[[0-9;]*m")
NOW = "2026-09-19T12:00:00+00:00"
WRAPPER = """
from datetime import datetime as RealDatetime
import importlib.util
import os
import sys
import time

time.tzset()
spec = importlib.util.spec_from_file_location('postbag_terminal_test', sys.argv[1])
postbag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(postbag)
fixed = RealDatetime.fromisoformat(os.environ['POSTBAG_TEST_NOW'])

class FixedDatetime(RealDatetime):
    @classmethod
    def now(cls, tz=None):
        return fixed.astimezone(tz) if tz is not None else fixed.astimezone().replace(tzinfo=None)

class Output:
    def __init__(self, stream):
        self.stream = stream
    def isatty(self):
        return os.environ['POSTBAG_TEST_TTY'] == '1'
    def __getattr__(self, name):
        return getattr(self.stream, name)

postbag.datetime = FixedDatetime
sys.stdout = Output(sys.stdout)
postbag.main(sys.argv[2:])
"""


@pytest.fixture
def terminal(inventory_cli):
    cli = inventory_cli

    def run(*args, columns=120, tty=True, extra=None, now=NOW, zone="UTC0"):
        environment = {key: value for key, value in cli.environment.items()
                       if key not in ("NO_COLOR", "TERM", "COLUMNS", "LINES", "TZ")}
        environment.update(
            COLUMNS=str(columns), LINES="30", TERM="xterm-256color", TZ=zone,
            POSTBAG_TEST_NOW=now, POSTBAG_TEST_TTY="1" if tty else "0",
        )
        environment.update(extra or {})
        return subprocess.run(
            [sys.executable, "-c", WRAPPER, str(SCRIPT), *args, "bags"],
            cwd=cli.cwd, env=environment, capture_output=True, text=True, timeout=3,
        )

    cli.terminal = run
    return cli


def plain(output):
    text = SGR.sub("", output)
    assert "\x1b" not in text, "only terminal SGR styling may be emitted"
    return text


def cells(text):
    """Screen cells for the combining and East Asian characters in these fixtures."""
    return sum(0 if unicodedata.combining(char) else
               2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
               for char in text)


def cell_slice(text, start, end=None):
    result, position, included = [], 0, False
    for char in text:
        width = cells(char)
        if width:
            included = position >= start and (end is None or position < end)
        if included:
            result.append(char)
        position += width
    return "".join(result)


def compact(text):
    return "".join(text.split())


def wide_columns(text):
    lines = text.splitlines()
    header_index = next(i for i, line in enumerate(lines)
                        if re.search(r"\bBag\s+Letters left\s+Last letter\s+Registered peers\b", line))
    header = lines[header_index]
    assert "|" not in header
    starts = [header.index(label) for label in ("Bag", "Letters left", "Last letter", "Registered peers")]
    body = lines[header_index + 1:]
    return ["\n".join(cell_slice(line, start, starts[i + 1] if i < 3 else None)
                      for line in body) for i, start in enumerate(starts)]


def dated(path, timestamp):
    rows = seed(path, opened(5), letter())
    rows[-1]["at"] = timestamp
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_wide_terminal_has_four_columns_and_omits_zero_summary_categories(terminal):
    cli = terminal
    seed(cli.default, opened(5))
    dated(cli.named / "review.jsonl", "2026-09-19T10:30:00+00:00")
    result = cli.terminal(columns=120)
    assert result.returncode == 0 and result.stderr == ""
    text = plain(result.stdout)
    wide_columns(text)
    first = next(line for line in text.splitlines() if line.strip())
    assert re.search(r"\b2\s+bags?\b", first, re.I)
    assert not re.search(r"\b0\s+(?:spent|never opened|unavailable)\b", first, re.I)
    assert "|" not in text


def test_terminal_orders_by_actual_last_letter_and_formats_local_times(terminal):
    cli = terminal
    stamps = {
        "future": "2026-09-19T13:30:00+00:00",
        "today": "2026-09-19T12:45:00+02:00",
        "legacy": "2026-09-19T10:15:00",
        "yesterday": "2026-09-18T23:00:00+00:00",
        "historical": "2026-09-16T07:45:00+00:00",
    }
    for name, timestamp in stamps.items():
        dated(cli.named / f"{name}.jsonl", timestamp)
    seed(cli.default, opened(5))
    result = cli.terminal(columns=120, extra={"NO_COLOR": "1"})
    assert result.returncode == 0 and result.stderr == ""
    text = plain(result.stdout)
    positions = [re.search(rf"(?m)^\s*{name}\b", text).start()
                 for name in (*stamps, "default")]
    assert positions == sorted(positions)
    assert "Today 10:45" in text and "Today 10:15" in text
    assert "Yesterday 23:00" in text and "2026-09-16 07:45" in text
    assert "2026-09-19 13:30" in text and re.search(r"future", text, re.I)
    future_entry = text[positions[0]:positions[1]]
    assert "2026-09-19 13:30" in future_entry
    assert re.search(r"future", future_entry.split("2026-09-19 13:30", 1)[1], re.I)


def test_local_date_boundary_uses_timezone_aware_and_legacy_timestamps_consistently(terminal):
    cli = terminal
    dated(cli.named / "aware.jsonl", "2026-09-19T00:15:00+00:00")
    dated(cli.named / "legacy.jsonl", "2026-09-18T19:10:00")
    result = cli.terminal(
        columns=120, zone="EST5", now="2026-09-19T00:30:00+00:00", extra={"NO_COLOR": "1"},
    )
    assert result.returncode == 0 and result.stderr == ""
    text = plain(result.stdout)
    assert "Today 19:15" in text and "Today 19:10" in text
    assert "Yesterday" not in text


def test_known_no_letters_and_unavailable_bag_remain_distinct(terminal):
    cli = terminal
    seed(cli.named / "empty.jsonl")
    broken = cli.named / "broken.jsonl"
    seed(broken)
    broken.write_bytes(b"not json\n")
    result = cli.terminal(columns=120, extra={"NO_COLOR": "1"})
    assert result.returncode == 1
    assert result.stderr.rstrip().endswith("; stop and ask the human")
    text = plain(result.stdout)
    empty_line = next(line for line in text.splitlines() if re.match(r"\s*empty\s", line))
    broken_line = next(line for line in text.splitlines() if re.match(r"\s*broken\s", line))
    assert "never opened" in empty_line.lower()
    assert "unavailable" in broken_line.lower()
    assert "unavailable" not in empty_line.lower()
    assert "no letters" not in broken_line.lower()


@pytest.mark.parametrize("columns", [40, 80, 120])
def test_terminal_wraps_all_paths_and_peer_names_without_losing_glyphs(terminal, columns):
    cli = terminal
    path = cli.cwd / ("分析" * 9 + "e\u0301" * 9) / ("full-custom-history-" * 5 + ".jsonl")
    names = ("alphabetasession", "betagammasession", "gammadeltasess", "deltalongsess")
    seed(path, *(joined(name, door=f"fake-door-{index}") for index, name in enumerate(names)), opened(7))
    before = fingerprint(path)
    result = cli.terminal("--bag", str(path), columns=columns, extra={"NO_COLOR": "1"})
    assert result.returncode == 0 and result.stderr == ""
    text = plain(result.stdout)
    assert all(cells(line) <= columns for line in text.splitlines()), text
    if columns >= 100:
        bag_column, _, _, peer_column = wide_columns(text)
        assert compact(str(path)) in compact(bag_column)
        assert "Codex:" in peer_column
        assert all(f"@{name}" in compact(peer_column) for name in names)
    else:
        assert compact(str(path)) in compact(text)
        assert "Codex:" in text
        assert all(f"@{name}" in compact(text) for name in names)
        assert not re.search(r"\bBag\s+Letters left\s+Last letter\s+Registered peers\b", text)
    assert fingerprint(path) == before


def test_wide_continuation_preserves_path_spaces_at_a_wrap_boundary(terminal):
    cli = terminal
    prefix = str(cli.cwd) + "/"
    # A long label uses the renderer's 26-cell label column. Place three real
    # filename spaces at a later wrap boundary, after all other cells finish.
    boundary = 26 * max(3, (len(prefix) + 3) // 26 + 2)
    path = cli.cwd / ("q" * (boundary - len(prefix) - 3) + "   ending.jsonl")
    seed(path, opened(2))
    before = fingerprint(path)
    result = cli.terminal("--bag", str(path), columns=120, extra={"NO_COLOR": ""})
    assert result.returncode == 0 and result.stderr == ""
    assert "\x1b" not in result.stdout
    expected_chunk = str(path)[boundary - 26:boundary]
    assert expected_chunk.endswith("   ")
    lines = result.stdout.splitlines()
    # Locate the fragment by its visible text, then compare the raw label cell:
    # rstrip() on the whole row would remove these actual filename characters.
    matches = [index for index, line in enumerate(lines)
               if cell_slice(line, 0, 26).rstrip() == expected_chunk.rstrip()]
    assert len(matches) == 1
    index = matches[0]
    assert cell_slice(lines[index], 0, 26) == expected_chunk
    assert cell_slice(lines[index + 1], 0, 26).startswith("ending.jsonl")
    assert fingerprint(path) == before


@pytest.mark.parametrize("extra, colored", [
    ({}, True), ({"NO_COLOR": ""}, False), ({"TERM": "dumb"}, False),
], ids=["interactive-color", "no-color-even-empty", "dumb-terminal"])
def test_terminal_color_obeys_environment_policy(terminal, extra, colored):
    cli = terminal
    seed(cli.default, opened(2))
    result = cli.terminal(columns=120, extra=extra)
    assert result.returncode == 0 and result.stderr == ""
    assert bool(SGR.search(result.stdout)) is colored
    plain(result.stdout)
    if not colored:
        assert "\x1b" not in result.stdout + result.stderr


def test_piped_output_stays_byte_identical_across_terminal_settings(terminal):
    cli = terminal
    dated(cli.default, "2026-09-16T07:00:00+00:00")
    dated(cli.named / "alpha.jsonl", "2026-09-18T19:00:00+02:00")
    dated(cli.named / "zeta.jsonl", "2026-09-19T10:00:00+00:00")
    baseline = cli.run("bags")
    assert baseline.returncode == 0 and baseline.stderr == ""
    assert list(table(baseline.stdout)) == ["default", "alpha", "zeta"]
    assert "2026-09-18T19:00:00+02:00" in baseline.stdout
    assert "0 spent, 0 never opened, 0 unavailable" in baseline.stdout
    for columns, extra in ((40, {}), (80, {"NO_COLOR": "1"}), (120, {"TERM": "dumb"})):
        result = cli.terminal(columns=columns, tty=False, extra=extra)
        assert (result.returncode, result.stdout, result.stderr) == (
            baseline.returncode, baseline.stdout, baseline.stderr,
        )
        assert "\x1b" not in result.stdout + result.stderr
