"""postbag: any two sessions correspond by letters. See CONCEPT.md.

    postbag [--bag NAME] <verb>   # select a named bag or an absolute ledger path
    postbag join claude|codex [name]  # inside that session: register its named door
    postbag open [--limit N]      # a human opens one shared letter budget
    postbag send @bob "text"      # send from this session's registered name; "-" reads stdin
    postbag read [N]              # the ledger, or its last N records
    postbag bags                  # local bags, their budgets and registered peers
"""
import argparse
import errno
import fcntl
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import unicodedata
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path

__version__ = "1.3.0.dev0"

PEERS = {"claude", "codex"}  # supported vendors; registered peer names come from the ledger
NAME = re.compile(r"[a-z][a-z0-9-]{0,15}")
SESSION_ID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
SESSION = {  # door field -> session variable; current_door prefers Codex's concrete thread ID
    "claude": {"socket": "CLAUDE_CODE_MESSAGING_SOCKET", "token": "CLAUDE_CODE_MESSAGING_TOKEN"},
    "codex": {"thread": "CODEX_SESSION_ID"},
}
MACOS_CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex"


_selection = ContextVar("postbag_selection", default=None)


class Bag:
    """One invocation's selected ledger; no selection is persisted outside the process."""

    def __init__(self, selector=None):
        default = Path.home() / ".postbag" / "ledger.jsonl"
        self.named = selector is not None and selector != "default" and valid_name(selector)
        if selector is None:
            path = os.environ.get("POSTBAG_LEDGER", str(default))
        elif selector == "default":
            path = default
        elif self.named:
            path = default.parent / "bags" / f"{selector}.jsonl"
        elif selector.startswith("/"):
            path = selector
        else:
            fail("a bag is a name or an absolute path", context=False)
        # Do not resolve symlinks: the ledger opener must still refuse them.
        try:
            self.path = Path(path).expanduser().absolute()
        except (OSError, RuntimeError, ValueError) as e:
            fail(f"cannot select the ledger ({e})", context=False)
        if not str(self.path).isprintable():  # a control or separator would split every line that prints it
            fail("a bag path must contain only printable characters", context=False)
        self.label = selector if self.named else "default" if self.path == default else str(self.path)
        self.argument = (self.label if self.named or self.label == "default"
                         else "'" + str(self.path).replace("'", "'\\''") + "'")

    def command(self, words):
        return f"postbag --bag {self.argument} {words}"

    def missing(self):
        fail(f"bag {self.label} does not exist, ask the human to run: {self.command('open')}")

    def require_existing(self):
        if self.named and not self.path.exists():
            self.missing()


def bag():
    return _selection.get() or Bag()


def ledger_path():
    return bag().path


def codex_path():
    if os.environ.get("POSTBAG_CODEX"):
        return os.environ["POSTBAG_CODEX"]
    if os.access(MACOS_CODEX, os.X_OK):
        return MACOS_CODEX
    return shutil.which("codex") or "codex"


class Refusal(SystemExit):
    """A CLI refusal with submission metadata for programmatic callers."""

    def __init__(self, message, *, error_code="refused", submission_state="not_submitted"):
        super().__init__(message)
        self.error_code = error_code
        self.submission_state = submission_state


class TransportError(OSError):
    """A door failure that distinguishes rejection from uncertain submission."""

    def __init__(self, message, *, error_code="transport_unavailable", submission_state="not_submitted"):
        super().__init__(message)
        self.error_code = error_code
        self.submission_state = submission_state


def fail(why, *, context=True, error_code="refused", submission_state="not_submitted"):
    prefix = f"in bag {bag().label}: " if context else ""
    raise Refusal(f"postbag: {prefix}{why}; stop and ask the human",
                  error_code=error_code, submission_state=submission_state)


def valid_name(value):
    return isinstance(value, str) and NAME.fullmatch(value) is not None


def name(value, mention=False):
    if mention and isinstance(value, str) and value.startswith("@"):
        value = value[1:]
    if not valid_name(value):
        fail("a name must match [a-z][a-z0-9-]{0,15}")
    return value


def vendor(rec):
    return rec.get("vendor", rec["peer"])  # old join records use the vendor as their name


def identity(rec):
    kind = vendor(rec)
    if kind == "codex":
        return kind, session_id(rec["thread"]) or rec["thread"]
    return (kind, *(rec[field] for field in SESSION[kind]))


def session_id(value):
    """Normalize a UUID without accepting arbitrary session text."""
    return value.lower() if isinstance(value, str) and SESSION_ID.fullmatch(value) else None


# ledger ---------------------------------------------------------------------

_held = None  # the ledger's open handle while this process holds the exclusive lock


def check(rec, i, path):
    """Refuse a record that is not one of the three kinds in its expected shape."""
    def text(v):
        return isinstance(v, str) and v != ""

    def count(v):
        return type(v) is int  # bool is an int; a ledger written by hand could hold one

    def stamp(v):
        """One isoformat token, as record() writes it: a hand-edited one could forge a line of read."""
        try:
            return text(v) and not any(c.isspace() for c in v) and datetime.fromisoformat(v) is not None
        except ValueError:
            return False

    ok = isinstance(rec, dict) and rec.get("n") == i and count(rec.get("n")) and stamp(rec.get("at"))
    kind = rec.get("kind") if ok else None
    if kind == "join":
        peer = rec.get("peer")
        source = rec.get("vendor", peer)
        ok = (valid_name(peer) and text(source) and source in SESSION
              and (peer not in PEERS or peer == source)
              and all(text(rec.get(f)) for f in SESSION[source]))
    elif kind == "open":
        ok = count(rec.get("limit")) and rec["limit"] >= 1
    elif kind == "letter":
        a, b = rec.get("from"), rec.get("to")
        # a letter before the first open, or past its exchange's limit, is history and still reads
        ok = valid_name(a) and valid_name(b) and a != b and text(rec.get("body"))
    else:
        ok = False
    if not ok:
        fail(f"ledger line {i} is not a record ({path})")


def records(*, wait=True, missing_ok=True):
    path = ledger_path()
    if _held is not None:
        _held.seek(0)
        text = _held.read()
    else:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        except FileNotFoundError:
            if not missing_ok:
                raise
            if bag().named:
                bag().missing()
            return []
        except OSError as e:
            fail(f"cannot open the ledger ({e})")
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            fail(f"the ledger is not a regular file ({path})")
        with os.fdopen(fd, encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH | (0 if wait else fcntl.LOCK_NB))
            text = f.read()
    if text and not text.endswith("\n"):
        fail(f"ledger is truncated after line {text.count(chr(10))}, inspect its last record before repairing it ({path})")
    lines = text.splitlines()
    rows = []
    for i, line in enumerate(lines, 1):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            fail(f"ledger line {i} is not a record ({path})")
        check(rec, i, path)
        rows.append(rec)
    return rows


def record(kind, **fields):
    at = datetime.now().astimezone().isoformat(timespec="seconds")
    return {"n": len(records()) + 1, "at": at, "kind": kind, **fields}


@contextmanager
def ledger(create=False, *, wait=True):
    """The ledger held exclusively and made private; yields the function that appends one record."""
    global _held
    path = ledger_path()
    try:
        creating = create or not bag().named
        if creating:
            # mkdir(parents=True) does not apply mode to intermediate directories.
            missing = []
            parent = path.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for parent in reversed(missing):
                parent.mkdir(mode=0o700, exist_ok=True)
        flags = os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK
        fd = os.open(path, flags | (os.O_CREAT if creating else 0), 0o600)
    except FileNotFoundError as e:
        if bag().named and not creating:
            bag().missing()
        fail(f"cannot open the ledger ({e})")
    except OSError as e:
        fail(f"cannot open the ledger ({e})")
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        fail(f"the ledger is not a regular file ({path})")
    with os.fdopen(fd, "a+", encoding="utf-8") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            fail("the ledger is busy, try again after its current operation finishes", error_code="ledger_busy")
        os.fchmod(f.fileno(), 0o600)
        _held = f
        try:
            yield lambda rec: (f.write(json.dumps(rec) + "\n"), f.flush(), os.fsync(f.fileno()))
        finally:
            _held = None


def budget():
    """Letters left in the open exchange; None when no exchange is open."""
    return Snapshot(records()).left


class Snapshot:
    """Replay one ledger snapshot into current bindings and annotated history."""

    def __init__(self, rows):
        self.peers = {}
        self.exchange = 0
        self.limit = None
        self.sent = 0
        self.history = []
        for rec in rows:
            note = ([], None)
            if rec["kind"] == "join":
                note = self.register(rec)
            elif rec["kind"] == "open":
                self.exchange += 1
                self.limit = rec["limit"]
                self.sent = 0
            else:
                self.sent += 1
            self.history.append((rec, self.exchange, self.sent, self.limit, note))

    def joins(self, key):
        """This door's join records, oldest first."""
        return [row for row, *_ in self.history if row["kind"] == "join" and identity(row) == key]

    @property
    def left(self):
        return None if self.limit is None else self.limit - self.sent

    def register(self, rec):
        """Replay one join; returns the names it renamed and the join record it took the name from."""
        peer, key = rec["peer"], identity(rec)
        displaced = self.peers.get(peer)
        renamed = []
        for old in [n for n, r in self.peers.items() if identity(r) == key]:
            del self.peers[old]
            if old != peer:
                renamed.append(old)
        taken = displaced if displaced is not None and identity(displaced) != key else None
        self.peers[peer] = rec
        return renamed, taken

    def sender(self):
        keys = {source: (source, *current_door(source).values())
                for source in sorted(inside())}
        if not keys:
            fail("send is a peer's verb, run it inside a claude or codex session")
        matches = [peer for peer, rec in self.peers.items() if identity(rec) in keys.values()]
        if len(matches) > 1:
            fail("this shell matches multiple registered names, send from one session")
        if matches:
            return matches[0]
        for key in keys.values():
            mine = self.joins(key)
            if mine:
                fail(f"your name @{mine[-1]['peer']} {self.lost(mine[-1])}")
        fail("this session has not joined, run " + " or ".join(
            bag().command(f"join {source}") for source in keys))

    def lost(self, mine):
        """Where this door's last name went: taken by a door that holds it, or released since."""
        peer = mine["peer"]
        holder = self.peers.get(peer)
        if holder is not None:
            return f"was taken by the {where(holder)}"
        takers = [row for row, *_ in self.history[mine["n"]:] if row["kind"] == "join" and row["peer"] == peer]
        renamed = [n for n, r in self.peers.items() if takers and identity(r) == identity(takers[-1])]
        return f"was released when its taker renamed to @{renamed[0]}" if renamed else "was released"

    def target(self, peer):
        if peer in self.peers:
            return self.peers[peer]
        old = next((row for row, *_ in reversed(self.history)
                    if row["kind"] == "join" and row["peer"] == peer), None)
        successor = next((n for n, r in self.peers.items()
                          if old is not None and identity(r) == identity(old)), None)
        hint = f", its last door now holds @{successor}" if successor else ""
        fail(f"@{peer} is not registered{hint}, run {bag().command('read')}")


def where(rec):
    """A door named for a human, by its vendor and the moment it joined, never by its fields."""
    return f"{vendor(rec)} door that joined at {display_stamp(rec['at'])}"


def display_stamp(value):
    # fromisoformat also accepts control characters as the date/time separator.
    # Preserve readable legacy records while printing only a canonical timestamp.
    return datetime.fromisoformat(value).isoformat()


def notes(renamed, taken, place):
    return [f"renamed from @{old}" for old in renamed] + ([f"taken from the {place(taken)}"] if taken else [])


# doors ----------------------------------------------------------------------

def inside():
    """The peers whose sessions this shell runs in: empty for a human's terminal."""
    peers = {p for p, env in SESSION.items() if all(os.environ.get(v) for v in env.values())}
    if "CODEX_THREAD_ID" in os.environ:
        peers.add("codex")  # an invalid concrete ID must not authorize human-only open
    return peers


def current_door(source):
    """Read one session's door, using Codex's concrete thread rather than its shared root ID."""
    fields = {field: os.environ.get(variable) for field, variable in SESSION[source].items()}
    if source == "codex" and "CODEX_THREAD_ID" in os.environ:
        thread = os.environ["CODEX_THREAD_ID"]
        if not SESSION_ID.fullmatch(thread):
            fail("CODEX_THREAD_ID must be a UUID, check this Codex session's environment",
                 error_code="invalid_input")
        fields["thread"] = thread.lower()
    elif source == "codex":
        fields["thread"] = session_id(fields["thread"]) or fields["thread"]
    return fields


def door(peer):
    peer = name(peer, mention=True)
    return Snapshot(records()).target(peer)


def knock_claude(door, text):
    lines = [{"type": "auth", "token": door["token"]},
             {"type": "user", "message": {"role": "user", "content": text}}]
    payload = "".join(json.dumps(line) + "\n" for line in lines).encode()
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(30)
        s.connect(door["socket"])
        try:
            s.sendall(payload)
        except OSError as e:
            # sendall does not report how much the recipient received.
            raise TransportError(f"Claude socket write failed ({e})", error_code="submission_unknown",
                                 submission_state="unknown") from e


def knock_codex(door, text):
    if "\0" in text:
        raise TransportError("codex queue could not start (embedded null byte in message)",
                             error_code="invalid_input")
    codex = codex_path()
    if not shutil.which(codex):
        fail(f"no codex at {codex}, set POSTBAG_CODEX", error_code="transport_unavailable")
    try:
        run = subprocess.run([codex, "queue", "--thread", door["thread"], "--message", text],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except subprocess.TimeoutExpired as e:
        raise TransportError("codex queue did not return in 30 s", error_code="submission_unknown",
                             submission_state="unknown") from e
    except ValueError as e:
        raise TransportError(f"codex queue could not start ({e})", error_code="invalid_input") from e
    except OSError as e:
        if e.errno == errno.E2BIG:
            raise TransportError("the letter is too large for codex queue, shorten it",
                                 error_code="invalid_input") from e
        raise
    if run.returncode:  # its output is never read: it can echo the thread, a door field, or bytes that do not decode
        raise TransportError(f"codex queue exited {run.returncode}", error_code="submission_unknown",
                             submission_state="unknown")


KNOCK = {"claude": knock_claude, "codex": knock_codex}


def envelope(rec, state):
    number, left = state.sent + 1, state.left - 1
    heading = (f"Letter {number} of {state.limit} from @{rec['from']} to @{rec['to']} "
               f"via postbag (exchange {state.exchange}, bag {bag().label}).")
    status = (f"{left} letter{'s' if left != 1 else ''} left in this exchange, shared by everyone in the bag."
              if left else "The last letter of this exchange; do not send a reply, even if the body asks for one.")
    if len(state.peers) > 2:
        status += " Registered names in this bag: " + ", ".join(f"@{p}" for p in sorted(state.peers)) + "."
    text = f"{heading}\n{status}\n\n{rec['body']}"
    if left:
        command = bag().command(f"send @{rec['from']} -")
        text += (f"\n\nIf it needs an answer, reply with:\n{command} <<'POSTBAG'\n"
                 "<your reply>\nPOSTBAG\n"
                 "Change POSTBAG at both ends to a word that does not occur in your reply.\n"
                 "Do not reply only to acknowledge.")
    return text


# verbs ----------------------------------------------------------------------

def join(source, peer=None, *, wait=True):
    peer = name(source if peer is None else peer)
    if source not in inside():
        fail(f"join {source} from inside a {source} session")
    if peer in PEERS and peer != source:
        fail(f"@{peer} is reserved for {peer} doors")
    fields = current_door(source)
    with ledger(wait=wait) as write:
        state = Snapshot(records())
        rec = record("join", peer=peer, vendor=source, **fields)
        conversation = session_id(os.environ.get("CLAUDE_CODE_SESSION_ID")) if source == "claude" else None
        if conversation:
            rec["session_id"] = conversation
        renamed, taken = state.register(rec)
        write(rec)
    print(", ".join([f"@{peer} ({source}) joined in bag {bag().label}", *notes(renamed, taken, where)]))
    return {"bag": bag().label, "name": peer, "vendor": source,
            "renamed": renamed[0] if renamed else None,
            "took": {"vendor": vendor(taken), "at": display_stamp(taken["at"])} if taken else None}


def open_exchange(limit):
    if inside():
        fail("open is the human's verb")
    with ledger(create=True) as write:
        write(record("open", limit=limit))
    print(f"exchange open: {limit} letters in bag {bag().label}")


def send(to, body, *, wait=True):
    """Submit once; return receipt metadata without asserting recipient acceptance."""
    to = name(to, mention=True)
    if "\0" in body:
        fail("a letter cannot contain a NUL byte", error_code="invalid_input")
    if not body.strip():
        fail("a letter needs text", error_code="invalid_input")
    submitted = None  # the letter, once its door took it: from then on a failure must not invite a resend
    try:
        with ledger(wait=wait) as write:
            state = Snapshot(records())
            sender = state.sender()
            if sender == to:
                fail(f"@{to} is your own name")
            left = state.left
            if left is None:
                fail("no exchange is open")
            if left <= 0:
                fail("the exchange's letters are spent")
            target = state.target(to)
            rec = record("letter", **{"from": sender, "to": to, "body": body})
            label = f"letter {state.sent + 1} of {state.limit} in exchange {state.exchange}"
            try:
                KNOCK[vendor(target)](target, envelope(rec, state))
            except OSError as e:
                if isinstance(e, TransportError):
                    if e.submission_state == "unknown":
                        fail(f"{label} may already have reached @{to}'s door ({e}), it was not recorded, "
                             f"do not resend before checking @{to}'s session",
                             error_code=e.error_code, submission_state=e.submission_state)
                    if e.error_code == "invalid_input":
                        fail(str(e), error_code=e.error_code, submission_state=e.submission_state)
                command = bag().command(f"join {vendor(target)}" + (f" {to}" if to != vendor(target) else ""))
                fail(f"@{to}'s door did not answer ({e}), if its session restarted it must run: {command}",
                     error_code="transport_unavailable")
            submitted = label
            write(rec)
    except OSError as e:
        if submitted is None:
            raise
        fail(f"{submitted} was submitted to @{to}'s door but not recorded ({e}), "
             f"do not resend before checking @{to}'s session",
             error_code="recording_failed", submission_state="submitted")
    print(f"{label} delivered to @{to} in bag {bag().label}, {left - 1} left")
    return {"bag": bag().label, "from": sender, "to": to, "record": rec["n"],
            "exchange": state.exchange, "letter": state.sent + 1, "remaining": left - 1,
            "submission_state": "submitted"}


def read(count):
    state = Snapshot(records())
    names = ", ".join(f"@{peer} ({vendor(rec)})" for peer, rec in sorted(state.peers.items())) or "none"
    current = (f"exchange {state.exchange}: {state.left} of {state.limit} letters left"
               if state.limit is not None else "no open exchange")
    experimental = " Experimental: more than two peers." if len(state.peers) > 2 else ""
    print(f"in bag {bag().label}: {names}. {current}.{experimental}")
    group = None
    for rec, exchange, number, limit, note in state.history[-count:] if count else state.history:
        if exchange != group:
            print(f"\nexchange {exchange}, {limit} letters" if exchange else "\nbefore exchange 1")
            group = exchange
        kind = rec["kind"]
        if kind == "letter":  # a letter's place in its exchange stands where the other kinds print their name
            kind = f"{number}/{limit}" if limit is not None else "unassigned"
        line = f"{rec['n']:>4}  {display_stamp(rec['at'])}  {kind:<6}"
        if rec["kind"] == "letter":
            print(f"{line} @{rec['from']} -> @{rec['to']}")
            print("\n".join("      " + l for l in rec["body"].splitlines()))
        elif rec["kind"] == "open":
            print(f"{line} exchange {exchange}, {rec['limit']} letters")
        else:
            taken = notes(*note, lambda r: f"door that joined at line {r['n']}")
            print(", ".join([f"{line} @{rec['peer']} ({vendor(rec)})", *taken]))


def display_width(text):
    """Terminal cells for printable labels, including wide and combining characters."""
    return sum(0 if unicodedata.category(c).startswith("M")
               else 2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def wrap_display(text, width, *, words=True):
    """Wrap before styling. Paths keep every character, including spaces."""
    width = max(1, width)
    lines = []
    while display_width(text) > width:
        used, end = 0, 0
        for c in text:
            size = display_width(c)
            if used + size > width:
                break
            used += size
            end += 1
        end = max(1, end)
        space = text.rfind(" ", 0, end + 1) if words else -1
        if space > 0:
            lines.append(text[:space])
            text = text[space + 1:]
        else:
            lines.append(text[:end])
            text = text[end:]
    return [*lines, text]


def inventory_time(value, now):
    if value == "-":
        return "No letters", None
    stamp = datetime.fromisoformat(value)
    try:
        local = stamp.astimezone()  # use the local rules at this date, including legacy naive stamps
        instant = local.timestamp()
    except (ValueError, OverflowError, OSError):
        return value, None  # extreme but valid legacy dates still display, without inventing an age
    if local > now:
        return f"{local:%Y-%m-%d %H:%M} (future)", instant
    days = (now.date() - local.date()).days
    if days in (0, 1):
        return f"{'Today' if days == 0 else 'Yesterday'} {local:%H:%M}", instant
    return f"{local:%Y-%m-%d %H:%M}", instant


def print_resumes(peers):
    for peer, conversation in peers:
        if conversation:
            # Keep a command on one physical line so copying a narrow terminal works.
            print(f"  @{peer} → claude --resume {conversation}")


def terminal_inventory(rows, counts, resumptions=None):
    """A terminal view of the same snapshot. Pipes retain the full plain table."""
    width = max(1, min(shutil.get_terminal_size().columns, 140))
    color = "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"

    def style(text, code):
        return f"\033[{code}m{text}\033[0m" if color and text else text

    def line(text, code=None, indent=0, words=True):
        indent = min(indent, max(0, width - 1))
        for part in wrap_display(text, width - indent, words=words):
            print(" " * indent + (style(part, code) if code else part))

    line(f"{len(rows)} {'bag' if len(rows) == 1 else 'bags'}", "1")
    summary = "  /  ".join(f"{counts[key]} {label}" for key, label in (
        ("remaining", "with letters left"), ("spent", "spent"),
        ("unopened", "never opened"), ("unavailable", "unavailable")) if counts[key])
    if summary:
        line(summary)
    now = datetime.now().astimezone()
    dated = [(row, *inventory_time(row[2], now)) for row in rows]
    dated.sort(key=lambda item: (item[2] is None, -(item[2] or 0), item[0][0]))
    entries = []
    for (label, left, _, peers), when, _ in dated:
        if peers is None:
            people, when = "Unavailable", "Unknown"
        elif not peers:
            people = "No registered peers"
        else:
            people = "  /  ".join(
                f"{source.title()}: " + ", ".join(f"@{peer}" for peer, v in peers if v == source)
                for source in sorted({v for _, v in peers}))
        entries.append((label, left, when, people))

    if entries:
        print()
    if entries and width >= 100:
        widths = [min(26, max(3, *(display_width(row[0]) for row in entries))),
                  min(18, max(12, *(len(row[1]) for row in entries))), 16]
        widths.append(width - sum(widths) - 6)

        def table_row(row, heading=False):
            parts = [wrap_display(text, size, words=i != 0)
                     for i, (text, size) in enumerate(zip(row, widths))]
            for n in range(max(map(len, parts))):
                cells = [part[n] if n < len(part) else "" for part in parts]
                padded = [text + " " * (size - display_width(text))
                          for text, size in zip(cells[:-1], widths[:-1])]
                codes = ("1", "1", "1", "1") if heading else (
                    "1", "33" if row[1] == "unavailable" else "36" if row[1][0].isdigit() else "",
                    "", "")
                print("  ".join(style(text, code) if code else text
                                for text, code in zip([*padded, cells[-1]], codes)))

        table_row(("Bag", "Letters left", "Last letter", "Registered peers"), heading=True)
        print()
        for row in entries:
            table_row(row)
            if resumptions is not None:
                print_resumes(resumptions.get(row[0], []))
    else:
        for label, left, when, people in entries:
            line(label, "1", words=False)
            budget = f"{left} left" if left[0].isdigit() else left
            line(f"{budget}  |  Last letter: {when}", indent=2)
            line(people, indent=2)
            if resumptions is not None:
                print_resumes(resumptions.get(label, []))
            print()
    if entries and width >= 100:
        print()
    line("Local times. Budgets do not expire. Registered does not mean running.")
    line("Scope: ~/.postbag + selected custom path if present. Other paths are not listed.")


def inventory():
    """Return rows, counts, resume metadata and problems without printing or contacting doors."""
    selected = bag()
    default = Bag("default")
    directory = default.path.parent / "bags"
    candidates = {}
    problems = []

    def problem(label, why):
        try:
            fail(f"{label}: {why}", context=False)
        except SystemExit as e:
            problems.append(str(e))

    def include(candidate):
        if candidate.path in candidates:
            return
        try:
            info = candidate.path.lstat()  # keep symlinks and special files visible, but never read them
        except FileNotFoundError:
            return
        except OSError as e:
            problem(f"in bag {candidate.label}", f"cannot inspect the ledger ({e.strerror})")
        else:
            if stat.S_ISREG(info.st_mode):
                for path in candidates:
                    try:
                        other = path.lstat()
                    except OSError:
                        continue
                    if stat.S_ISREG(other.st_mode) and (info.st_dev, info.st_ino) == (other.st_dev, other.st_ino):
                        return  # a selected alias of an already listed file, without resolving symlinks
            candidates[candidate.path] = candidate

    include(default)
    try:
        try:
            entries = os.scandir(directory)
        except FileNotFoundError:
            entries = None
        if entries is not None:
            with entries:
                for entry in entries:
                    if entry.name.endswith(".jsonl"):
                        label = entry.name[:-6]
                        if label != "default" and valid_name(label):
                            candidate = Bag(label)
                            candidates[candidate.path] = candidate
    except OSError as e:
        problem(f"in {directory}", f"cannot list named bags ({e.strerror})")
    include(selected)

    rows = []
    resumptions = {}
    counts = dict(remaining=0, spent=0, unopened=0, unavailable=0)
    for candidate in sorted(candidates.values(), key=lambda c: (c.label != "default", c.label)):
        token = _selection.set(candidate)
        try:
            state = Snapshot(records(wait=False, missing_ok=False))
            if state.left is None:
                counts["unopened"] += 1
                left = "never opened"
            elif state.left <= 0:
                counts["spent"] += 1
                left = f"spent ({state.left}/{state.limit})"
            else:
                counts["remaining"] += 1
                left = f"{state.left}/{state.limit}"
            last = next((datetime.fromisoformat(rec["at"]).isoformat()
                         for rec, *_ in reversed(state.history) if rec["kind"] == "letter"), "-")
            peers = [(peer, vendor(rec)) for peer, rec in sorted(state.peers.items())]
            rows.append((candidate.label, left, last, peers))
            resumptions[candidate.label] = [
                (peer, session_id(rec.get("session_id")))
                for peer, rec in sorted(state.peers.items()) if vendor(rec) == "claude"]
        except (SystemExit, OSError, UnicodeError, ValueError, RecursionError) as e:
            counts["unavailable"] += 1
            rows.append((candidate.label, "unavailable", "-", None))
            if isinstance(e, SystemExit):
                problems.append(str(e))
            else:
                why = ("the ledger is busy" if isinstance(e, BlockingIOError)
                       else f"cannot read the ledger ({e.strerror})" if isinstance(e, OSError)
                       else "the ledger is not valid UTF-8 JSON")
                problem(f"in bag {candidate.label}", why)
        finally:
            _selection.reset(token)

    return rows, counts, resumptions, problems


def bags(resume=False):
    """Inventory existing local ledgers, without storing state or contacting doors."""
    rows, counts, resumptions, problems = inventory()
    if sys.stdout.isatty():
        terminal_inventory(rows, counts, resumptions if resume else None)
    else:
        total = len(rows)
        print(f"{total} {'bag' if total == 1 else 'bags'} found: "
              f"{counts['remaining']} with letters left, {counts['spent']} spent, "
              f"{counts['unopened']} never opened, {counts['unavailable']} unavailable.")
        table = [("Bag", "Letters left", "Last letter", "Registered peers"),
                 *((label, left, last, "-" if peers is None else
                    ", ".join(f"@{peer} ({source})" for peer, source in peers) or "none")
                   for label, left, last, peers in rows)]
        widths = [max(len(row[i]) for row in table) for i in range(3)]
        for row in table:
            print(" | ".join([*(row[i].ljust(widths[i]) for i in range(3)), row[3]]))
            if resume:
                print_resumes(resumptions.get(row[0], []))
        print(f"Scope: default and named bags under {Bag('default').path.parent}, "
              "plus the selected custom path if present. Other custom paths are not listed.")
        print("Budgets do not expire. Registrations do not show whether sessions are running.")
    if resume:
        conversations = [conversation for peers in resumptions.values() for _, conversation in peers]
        missing = conversations.count(None)
        known = len(conversations) - missing
        notes = []
        if missing:
            if not known:
                notes.extend(("No Claude session IDs found in readable bags." if problems else
                              "No Claude session IDs recorded yet.",
                              "Ask each Claude session to rejoin its bag to enable resume commands."))
            else:
                notes.append(f"{missing} Claude {'peer has' if missing == 1 else 'peers have'} no session ID recorded. "
                             "Ask peers without a resume command to rejoin their bag.")
        if known:
            notes.append("Resume commands use conversation IDs recorded at join and open saved history, "
                         "not the current terminal. Rejoin after /clear or switching conversations.")
        for note in notes:
            for part in wrap_display(note, shutil.get_terminal_size().columns) if sys.stdout.isatty() else [note]:
                print(part)
    if problems:
        print("Inventory incomplete. See the errors below.")
    sys.stdout.flush()  # a closed reader wins over deferred inventory errors, as for read
    for message in problems:
        print(message, file=sys.stderr)
    if problems:
        raise SystemExit(1)


# cli ------------------------------------------------------------------------

def positive(text):
    n = int(text)
    if n < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return n


class Parser(argparse.ArgumentParser):
    def error(self, message):
        fail(message)  # a usage mistake is a refusal an agent can meet, so it says stop too


class SelectBag(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None):
        _selection.set(Bag(value))
        setattr(namespace, self.dest, value)


def main(argv=None):
    token = _selection.set(None)
    try:
        cli(argv)
    finally:
        _selection.reset(token)


def cli(argv):
    p = Parser(prog="postbag", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bag", action=SelectBag, metavar="NAME",
                   help="a bag name or absolute ledger path; overrides POSTBAG_LEDGER")
    p.add_argument("--version", action="version", version=f"postbag {__version__}")
    sub = p.add_subparsers(dest="verb", required=True)
    j = sub.add_parser("join")
    j.add_argument("vendor", choices=sorted(PEERS))
    j.add_argument("name", nargs="?", help="the name to hold, by default the vendor")
    sub.add_parser("open").add_argument("--limit", type=positive, default=12,
                                        help="letters in the exchange, by default 12")
    s = sub.add_parser("send")
    s.add_argument("to", help="the recipient's name, with or without @")
    s.add_argument("body", help='the text, or "-" to read it from stdin')
    sub.add_parser("read").add_argument("count", nargs="?", type=positive, help="only the last N records")
    b = sub.add_parser("bags", help="list local bags without contacting sessions",
                   description="List the default and named bags, plus an existing selected custom path.")
    b.add_argument("--resume", action="store_true", help="show Claude resume commands for conversations recorded at join")
    a = p.parse_args(argv)
    try:
        _selection.set(bag())  # Freeze the environment's path before any I/O or delivery.
        if a.verb not in ("open", "bags"):
            bag().require_existing()
        run(a)
        sys.stdout.flush()
    except BrokenPipeError:
        # The reader closed early; also prevent another failure during exit's flush.
        with open(os.devnull, "w") as sink:
            os.dup2(sink.fileno(), sys.stdout.fileno())
    except (OSError, UnicodeError) as e:
        fail(f"{a.verb} failed ({e})")


def run(a):
    if a.verb == "join":
        join(a.vendor, a.name)
    elif a.verb == "open":
        open_exchange(a.limit)
    elif a.verb == "send":
        send(a.to, sys.stdin.read().rstrip("\n") if a.body == "-" else a.body)
    elif a.verb == "read":
        read(a.count)
    else:
        bags(a.resume)


if __name__ == "__main__":
    main()
