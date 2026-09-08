"""postbag: two agents correspond by letters. See CONCEPT.md.

    postbag join claude|codex     # inside that session: publish its door
    postbag open [--limit N]      # a human, outside both sessions: an exchange of at most N letters
    postbag send codex "text"     # a letter from claude to codex; "-" reads the body from stdin
    postbag read [N]              # the ledger, or its last N records
"""
import argparse
import fcntl
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

__version__ = "1.0.0"

PEERS = {"claude", "codex"}
SESSION = {  # door field -> the variable each vendor exports inside its own session
    "claude": {"socket": "CLAUDE_CODE_MESSAGING_SOCKET", "token": "CLAUDE_CODE_MESSAGING_TOKEN"},
    "codex": {"thread": "CODEX_SESSION_ID"},
}
MACOS_CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex"


def ledger_path():
    return Path(os.environ.get("POSTBAG_LEDGER", "~/.postbag/ledger.jsonl")).expanduser()


def codex_path():
    if os.environ.get("POSTBAG_CODEX"):
        return os.environ["POSTBAG_CODEX"]
    if os.access(MACOS_CODEX, os.X_OK):
        return MACOS_CODEX
    return shutil.which("codex") or "codex"


def fail(why):
    sys.exit(f"postbag: {why}; stop and ask the human")


# ledger ---------------------------------------------------------------------

_held = None  # the ledger's open handle while this process holds the exclusive lock


def check(rec, i, path):
    """Refuse a record that is not one of the three kinds in its expected shape."""
    def text(v):
        return isinstance(v, str) and v != ""

    def count(v):
        return type(v) is int  # bool is an int; a ledger written by hand could hold one

    ok = isinstance(rec, dict) and rec.get("n") == i and count(rec.get("n")) and text(rec.get("at"))
    kind = rec.get("kind") if ok else None
    if kind == "join":
        peer = rec.get("peer")
        ok = text(peer) and peer in PEERS and all(text(rec.get(f)) for f in SESSION[peer])
    elif kind == "open":
        ok = count(rec.get("limit")) and rec["limit"] >= 1
    elif kind == "letter":
        a, b = rec.get("from"), rec.get("to")
        ok = text(a) and text(b) and a in PEERS and b in PEERS and a != b and text(rec.get("body"))
    else:
        ok = False
    if not ok:
        fail(f"ledger line {i} is not a record ({path})")


def records():
    path = ledger_path()
    if _held is not None:
        _held.seek(0)
        lines = _held.read().splitlines()
    elif path.exists():
        with path.open(encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            lines = f.read().splitlines()
    else:
        return []
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
def ledger():
    """The ledger held exclusively and made private; yields the function that appends one record."""
    global _held
    path = ledger_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
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
    sent = 0
    for rec in reversed(records()):
        if rec["kind"] == "open":
            return rec["limit"] - sent
        sent += rec["kind"] == "letter"
    return None


# doors ----------------------------------------------------------------------

def inside():
    """The peers whose sessions this shell runs in: empty for a human's terminal."""
    return {p for p, env in SESSION.items() if all(os.environ.get(v) for v in env.values())}


def door(peer):
    joins = [r for r in records() if r["kind"] == "join" and r["peer"] == peer]
    return joins[-1] if joins else fail(f"{peer} has not joined")


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
        fail(f"no codex at {codex}; set POSTBAG_CODEX")
    try:
        run = subprocess.run([codex, "queue", "--thread", door["thread"], "--message", text],
                             capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise OSError("codex queue did not return in 30 s")
    if run.returncode:
        raise OSError(run.stderr.strip() or f"codex queue exited {run.returncode}")


KNOCK = {"claude": knock_claude, "codex": knock_codex}


def envelope(rec, left):
    if left:
        answer = (f"If it needs an answer, reply with:\npostbag send {rec['from']} - <<'POSTBAG'\n...\nPOSTBAG\n"
                  "Choose a delimiter that does not occur in your reply. Otherwise do nothing.")
    else:
        answer = "It is the last letter of the exchange; do not reply."
    return f"Letter {rec['n']} from {rec['from']} via postbag. {answer}\n\n{rec['body']}"


# verbs ----------------------------------------------------------------------

def join(peer):
    if peer not in inside():
        fail(f"join {peer} from inside a {peer} session")
    with ledger() as write:
        write(record("join", peer=peer, **{field: os.environ[var] for field, var in SESSION[peer].items()}))
    print(f"{peer} joined")


def open_exchange(limit):
    if inside():
        fail("open is the human's verb")
    with ledger() as write:
        write(record("open", limit=limit))
    print(f"exchange open: {limit} letters")


def send(to, body):
    sender = (PEERS - {to}).pop()
    if sender not in inside():
        fail(f"send {to} is {sender}'s verb; run it inside a {sender} session")
    if not body.strip():
        fail("a letter needs text")
    with ledger() as write:
        left = budget()
        if left is None:
            fail("no exchange is open")
        if left <= 0:
            fail("the exchange's letters are spent")
        rec = record("letter", **{"from": sender, "to": to, "body": body})
        try:
            KNOCK[to](door(to), envelope(rec, left - 1))
        except OSError as e:
            fail(f"{to}'s door did not answer ({e}); if its session restarted it must run: postbag join {to}")
        try:
            write(rec)
        except OSError as e:
            fail(f"letter {rec['n']} was submitted to {to}'s door but not recorded ({e}); do not resend before checking {to}'s session")
    print(f"letter {rec['n']} delivered to {to}, {left - 1} left")


def read(count):
    rows = records()
    for rec in rows[-count:] if count else rows:
        line = f"{rec['n']:>4}  {rec['at']}  {rec['kind']:<6}"
        if rec["kind"] == "letter":
            print(f"{line} {rec['from']} -> {rec['to']}")
            print("\n".join("      " + l for l in rec["body"].splitlines()))
        elif rec["kind"] == "open":
            print(f"{line} {rec['limit']} letters")
        else:
            print(f"{line} {rec['peer']}")


# cli ------------------------------------------------------------------------

def positive(text):
    n = int(text)
    if n < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return n


def main(argv=None):
    p = argparse.ArgumentParser(prog="postbag", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"postbag {__version__}")
    sub = p.add_subparsers(dest="verb", required=True)
    sub.add_parser("join").add_argument("peer", choices=sorted(PEERS))
    sub.add_parser("open").add_argument("--limit", type=positive, default=12)
    s = sub.add_parser("send")
    s.add_argument("to", choices=sorted(PEERS))
    s.add_argument("body", help='the text, or "-" to read it from stdin')
    sub.add_parser("read").add_argument("count", nargs="?", type=positive)
    a = p.parse_args(argv)
    try:
        run(a)
    except (OSError, UnicodeError) as e:
        fail(f"{a.verb} failed ({e})")


def run(a):
    if a.verb == "join":
        join(a.peer)
    elif a.verb == "open":
        open_exchange(a.limit)
    elif a.verb == "send":
        send(a.to, sys.stdin.read().rstrip("\n") if a.body == "-" else a.body)
    else:
        read(a.count)


if __name__ == "__main__":
    main()
