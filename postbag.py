"""postbag: any two sessions correspond by letters. See CONCEPT.md.

    postbag [--bag NAME] <verb>   # select a named bag or an absolute ledger path
    postbag join claude|codex [name]  # inside that session: register its named door
    postbag open [--limit N]      # a human opens one shared letter budget
    postbag send @bob "text"      # send from this session's registered name; "-" reads stdin
    postbag read [N]              # the ledger, or its last N records
"""
import argparse
import fcntl
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path

__version__ = "1.2.0"

PEERS = {"claude", "codex"}  # supported vendors; registered peer names come from the ledger
NAME = re.compile(r"[a-z][a-z0-9-]{0,15}")
SESSION = {  # door field -> the variable each vendor exports inside its own session
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


def fail(why, *, context=True):
    prefix = f"in bag {bag().label}: " if context else ""
    sys.exit(f"postbag: {prefix}{why}; stop and ask the human")


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
    return (kind, *(rec[field] for field in SESSION[kind]))


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


def records():
    path = ledger_path()
    if _held is not None:
        _held.seek(0)
        text = _held.read()
    else:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        except FileNotFoundError:
            if bag().named:
                bag().missing()
            return []
        except OSError as e:
            fail(f"cannot open the ledger ({e})")
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            fail(f"the ledger is not a regular file ({path})")
        with os.fdopen(fd, encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
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
def ledger(create=False):
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
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "a+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
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
        keys = {source: (source, *(os.environ[var] for var in SESSION[source].values()))
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
    return f"{vendor(rec)} door that joined at {rec['at']}"


def notes(renamed, taken, place):
    return [f"renamed from @{old}" for old in renamed] + ([f"taken from the {place(taken)}"] if taken else [])


# doors ----------------------------------------------------------------------

def inside():
    """The peers whose sessions this shell runs in: empty for a human's terminal."""
    return {p for p, env in SESSION.items() if all(os.environ.get(v) for v in env.values())}


def door(peer):
    peer = name(peer, mention=True)
    return Snapshot(records()).target(peer)


def knock_claude(door, text):
    lines = [{"type": "auth", "token": door["token"]},
             {"type": "user", "message": {"role": "user", "content": text}}]
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(30)
        s.connect(door["socket"])
        s.sendall("".join(json.dumps(line) + "\n" for line in lines).encode())


def knock_codex(door, text):
    codex = codex_path()
    if not shutil.which(codex):
        fail(f"no codex at {codex}, set POSTBAG_CODEX")
    try:
        run = subprocess.run([codex, "queue", "--thread", door["thread"], "--message", text],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except subprocess.TimeoutExpired:
        raise OSError("codex queue did not return in 30 s")
    if run.returncode:  # its output is never read: it can echo the thread, a door field, or bytes that do not decode
        raise OSError(f"codex queue exited {run.returncode}")


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

def join(source, peer=None):
    peer = name(source if peer is None else peer)
    if source not in inside():
        fail(f"join {source} from inside a {source} session")
    if peer in PEERS and peer != source:
        fail(f"@{peer} is reserved for {peer} doors")
    with ledger() as write:
        state = Snapshot(records())
        rec = record("join", peer=peer, vendor=source,
                     **{field: os.environ[var] for field, var in SESSION[source].items()})
        renamed, taken = state.register(rec)
        write(rec)
    print(", ".join([f"@{peer} ({source}) joined in bag {bag().label}", *notes(renamed, taken, where)]))


def open_exchange(limit):
    if inside():
        fail("open is the human's verb")
    with ledger(create=True) as write:
        write(record("open", limit=limit))
    print(f"exchange open: {limit} letters in bag {bag().label}")


def send(to, body):
    to = name(to, mention=True)
    if not body.strip():
        fail("a letter needs text")
    submitted = None  # the letter, once its door took it: from then on a failure must not invite a resend
    try:
        with ledger() as write:
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
                command = bag().command(f"join {vendor(target)}" + (f" {to}" if to != vendor(target) else ""))
                fail(f"@{to}'s door did not answer ({e}), if its session restarted it must run: {command}")
            submitted = label
            write(rec)
    except OSError as e:
        if submitted is None:
            raise
        fail(f"{submitted} was submitted to @{to}'s door but not recorded ({e}), "
             f"do not resend before checking @{to}'s session")
    print(f"{label} delivered to @{to} in bag {bag().label}, {left - 1} left")


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
        line = f"{rec['n']:>4}  {rec['at']}  {kind:<6}"
        if rec["kind"] == "letter":
            print(f"{line} @{rec['from']} -> @{rec['to']}")
            print("\n".join("      " + l for l in rec["body"].splitlines()))
        elif rec["kind"] == "open":
            print(f"{line} exchange {exchange}, {rec['limit']} letters")
        else:
            taken = notes(*note, lambda r: f"door that joined at line {r['n']}")
            print(", ".join([f"{line} @{rec['peer']} ({vendor(rec)})", *taken]))


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
    a = p.parse_args(argv)
    try:
        _selection.set(bag())  # Freeze the environment's path before any I/O or delivery.
        if a.verb != "open":
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
    else:
        read(a.count)


if __name__ == "__main__":
    main()
