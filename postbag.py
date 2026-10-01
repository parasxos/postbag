"""postbag: any two sessions correspond by letters. See CONCEPT.md.

    postbag [--bag NAME] <verb>   # select a named bag or an absolute ledger path
    postbag join claude|codex [name]  # inside that session: register its named door, creating the bag
    postbag send [--final] @bob "text"  # send from this session's registered name; "-" reads stdin
    postbag read [N]              # the ledger, or its last N records
    postbag bags                  # local bags, their letters and registered peers
    postbag leave                 # inside a session: withdraw this door's name from the bag
    postbag mcp                   # start the optional MCP server on stdio, the same as postbag-mcp
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

__version__ = "2.2.1"

PEERS = {"claude", "codex"}  # supported vendors; registered peer names come from the ledger
NAME = re.compile(r"[a-z][a-z0-9-]{0,15}")
SESSION_ID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
SESSION = {  # door field -> session variable; current_door prefers Codex's concrete thread ID
    "claude": {"socket": "CLAUDE_CODE_MESSAGING_SOCKET", "token": "CLAUDE_CODE_MESSAGING_TOKEN"},
    "codex": {"thread": "CODEX_SESSION_ID"},
}
MACOS_CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex"
# Never inherited by the codex child: the sender's own door fields and postbag's selection.
HIDDEN_FROM_CHILD = ({variable for fields in SESSION.values() for variable in fields.values()}
                     | {"CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "POSTBAG_LEDGER"})


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

    def absent(self, verb):
        """Refuse a verb on a bag that does not exist. Nothing is created, not even a directory."""
        if verb == "send":
            sources = sorted(inside())
            commands = " or ".join(self.command(f"join {source}") for source in sources or sorted(PEERS))
            who = "create it from your session with" if sources else "a peer creates it from its session with"
            fail(f"bag {self.label} does not exist, {who}: {commands}",
                 recovery={"action": "join", "actor": "caller", "bag": self.label,
                           "vendor": sources[0] if len(sources) == 1 else None, "name": None})
        fail(f"bag {self.label} does not exist, run: postbag bags",
             recovery={"action": "bags", "actor": "caller", "bag": self.label})


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
    """A CLI refusal with submission metadata for programmatic callers.

    recovery, when present, names the one step that clears the refusal: an action
    (join, read or bags), who performs it (caller or recipient), the bag, and for a
    join the vendor and name when they are known. The message text stays the
    contract for humans, and recovery is the same advice for programs.
    """

    def __init__(self, message, *, error_code="refused", submission_state="not_submitted", recovery=None):
        super().__init__(message)
        self.error_code = error_code
        self.submission_state = submission_state
        self.recovery = recovery


class TransportError(OSError):
    """A door failure that distinguishes rejection from uncertain submission."""

    def __init__(self, message, *, error_code="transport_unavailable", submission_state="not_submitted"):
        super().__init__(message)
        self.error_code = error_code
        self.submission_state = submission_state


def fail(why, *, context=True, error_code="refused", submission_state="not_submitted", recovery=None):
    prefix = f"in bag {bag().label}: " if context else ""
    raise Refusal(f"postbag: {prefix}{why}; stop and ask the human",
                  error_code=error_code, submission_state=submission_state, recovery=recovery)


def encodable(value):
    """True when a string is valid Unicode text: no lone surrogates from surrogateescape."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


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
    """Refuse a record that is not one of the four kinds in its expected shape."""
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
    if kind in ("join", "leave"):  # a leave names the door it withdraws as its join did, vendor spelled out
        peer = rec.get("peer")
        source = rec.get("vendor", peer if kind == "join" else None)  # only old joins used the vendor as their name
        ok = (valid_name(peer) and text(source) and source in SESSION
              and (peer not in PEERS or peer == source)
              and all(text(rec.get(f)) for f in SESSION[source]))
    elif kind == "open":  # written by 1.x, inert history that still has to be well formed
        ok = count(rec.get("limit")) and rec["limit"] >= 1
    elif kind == "letter":
        a, b = rec.get("from"), rec.get("to")
        ok = (valid_name(a) and valid_name(b) and a != b and text(rec.get("body"))
              and ("final" not in rec or type(rec["final"]) is bool))
    else:
        ok = False
    if not ok:
        fail(f"ledger line {i} is not a record ({path})")


def records(*, wait=True, refuse_missing=True):
    """Every record of the selected ledger. A missing ledger refuses and points to bags,
    unless the caller asked for the FileNotFoundError itself. Nothing is ever created."""
    path = ledger_path()
    if _held is not None:
        _held.seek(0)
        text = _held.read()
    else:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        except FileNotFoundError:
            if not refuse_missing:
                raise
            bag().absent("read")
        except OSError as e:
            fail(f"cannot open the ledger ({e})")
        try:  # the raw descriptor is owned here until the file object takes it
            regular = stat.S_ISREG(os.fstat(fd).st_mode)
            f = os.fdopen(fd, encoding="utf-8") if regular else None
        except BaseException:
            os.close(fd)
            raise
        if f is None:
            os.close(fd)
            fail(f"the ledger is not a regular file ({path})")
        with f:
            fcntl.flock(f, fcntl.LOCK_SH | (0 if wait else fcntl.LOCK_NB))
            text = f.read()
    if text and not text.endswith("\n"):
        fail(f"ledger is truncated after line {text.count(chr(10))}, inspect its last record before repairing it ({path})")
    lines = text.splitlines()
    rows = []
    for i, line in enumerate(lines, 1):
        try:
            rec = json.loads(line)
        except ValueError:  # JSONDecodeError, or a plain ValueError for an integer past the digit limit
            fail(f"ledger line {i} is not a record ({path})")
        check(rec, i, path)
        rows.append(rec)
    return rows


def record(kind, **fields):
    at = datetime.now().astimezone().isoformat(timespec="seconds")
    return {"n": len(records()) + 1, "at": at, "kind": kind, **fields}


def exposed(mode):
    """Why an existing ledger's mode disqualifies it from any mutation, or None."""
    if mode & 0o077:
        return "the ledger grants other users access, fix its mode to 0600"
    if mode & 0o600 != 0o600:
        return "the ledger lacks owner read and write"
    return None


@contextmanager
def ledger(create=False, *, wait=True, verb="send"):
    """The ledger held exclusively. Yields the function that appends one record.

    Only join passes create=True. Creation is established by one O_CREAT|O_EXCL open and
    by nothing else: when that open finds the file already there, the file is opened as it
    is. A created file gets mode 0600. An existing file is never re-moded, and a mode that
    grants group or other access, or lacks owner read and write, refuses before any parse,
    knock or append. Without create, a missing ledger refuses as the named verb does: send
    points to join, every other verb points to bags.
    """
    global _held
    path = ledger_path()
    flags = os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK
    created = False
    try:
        if create:
            # mkdir(parents=True) does not apply mode to intermediate directories.
            missing = []
            parent = path.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for parent in reversed(missing):
                parent.mkdir(mode=0o700, exist_ok=True)
            try:
                fd = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
                created = True
            except FileExistsError:
                fd = os.open(path, flags)
        else:
            fd = os.open(path, flags)
    except FileNotFoundError as e:
        if not create:
            bag().absent(verb)
        fail(f"cannot open the ledger ({e})")
    except OSError as e:
        fail(f"cannot open the ledger ({e})")
    try:  # the raw descriptor is ours until fdopen owns it, so any failure here must close it
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            fail(f"the ledger is not a regular file ({path})")
        f = os.fdopen(fd, "a+", encoding="utf-8")
    except BaseException:
        os.close(fd)
        raise
    with f:
        if created:
            os.fchmod(f.fileno(), 0o600)  # the open mode is subject to the umask
        try:
            fcntl.flock(f, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            fail("the ledger is busy, read the bag before doing anything else", error_code="ledger_busy",
                 recovery={"action": "read", "actor": "caller", "bag": bag().label})
        if not created:
            why = exposed(stat.S_IMODE(os.fstat(f.fileno()).st_mode))
            if why:
                fail(why)
        _held = f
        try:
            yield lambda rec: (f.write(json.dumps(rec) + "\n"), f.flush(), os.fsync(f.fileno()))
        finally:
            _held = None


class Snapshot:
    """Replay one ledger snapshot into current bindings and annotated history.

    peers maps each held name to its join record. letters counts the bag's letters.
    history holds one (rec, letter, note) per record: letter is the record's position
    among the bag's letters, or None for the other kinds, and note is the (renamed, taken)
    pair of a join, or ([], None) otherwise. A leave removes a binding and is ([], None).
    """

    def __init__(self, rows):
        self.peers = {}
        self.letters = 0
        self.history = []
        for rec in rows:
            note, letter = ([], None), None
            if rec["kind"] == "join":
                note = self.register(rec)
            elif rec["kind"] == "leave":
                self.withdraw(rec)
            elif rec["kind"] == "letter":
                self.letters += 1
                letter = self.letters
            self.history.append((rec, letter, note))

    def transitions(self, key):
        """This door's join and leave records, oldest first."""
        return [row for row, *_ in self.history if row["kind"] in ("join", "leave") and identity(row) == key]

    def last(self, peer):
        """The latest join or leave naming this peer, or None."""
        return next((row for row, *_ in reversed(self.history)
                     if row["kind"] in ("join", "leave") and row["peer"] == peer), None)

    def left(self, peer):
        """The leave record that is this name's latest transition, or None."""
        last = self.last(peer)
        return last if last is not None and last["kind"] == "leave" else None

    def withdraw(self, rec):
        """Replay one leave: the name must still be held by exactly the door that leaves."""
        peer = rec["peer"]
        held = self.peers.get(peer)
        if held is None or identity(held) != identity(rec):
            fail(f"ledger line {rec['n']} leaves @{peer}, which that door does not hold ({ledger_path()})")
        del self.peers[peer]

    def held_by(self, keys, verb):
        """The names held by any of these doors, or a refusal when a shell matches several."""
        matches = [peer for peer, rec in self.peers.items() if identity(rec) in keys]
        if len(matches) > 1:
            fail(f"this shell matches multiple registered names, {verb} from one session")
        return matches

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
        matches = self.held_by(keys.values(), "send")
        if matches:
            return matches[0]
        rejoin = {"action": "join", "actor": "caller", "bag": bag().label,
                  "vendor": next(iter(keys)) if len(keys) == 1 else None, "name": None}
        for source, key in keys.items():
            mine = self.transitions(key)
            if mine and mine[-1]["kind"] == "leave":  # this door withdrew: an old queued letter must not talk it back in
                fail(f"your name @{mine[-1]['peer']} left this bag at {display_stamp(mine[-1]['at'])}, "
                     "do not join again unless the human asks you to resume",
                     recovery={"action": "read", "actor": "caller", "bag": bag().label})
            if mine:
                fail(f"your name @{mine[-1]['peer']} {self.lost(mine[-1])}", recovery=rejoin)
        fail("this session has not joined, run " + " or ".join(
            bag().command(f"join {source}") for source in keys), recovery=rejoin)

    def lost(self, mine):
        """Where this door's last name went: taken by a door that holds it, taken by a door
        that left with it, or released since."""
        peer = mine["peer"]
        holder = self.peers.get(peer)
        if holder is not None:
            return f"was taken by the {where(holder)}"
        takers = [row for row, *_ in self.history[mine["n"]:] if row["kind"] == "join" and row["peer"] == peer]
        gone = self.left(peer)
        if takers and gone is not None and identity(gone) == identity(takers[-1]):
            return f"was taken by the {where(takers[-1])}, which left this bag at {display_stamp(gone['at'])}"
        renamed = [n for n, r in self.peers.items() if takers and identity(r) == identity(takers[-1])]
        return f"was released when its taker renamed to @{renamed[0]}" if renamed else "was released"

    def target(self, peer):
        if peer in self.peers:
            return self.peers[peer]
        old = self.last(peer)
        successor = next((n for n, r in self.peers.items()
                          if old is not None and identity(r) == identity(old)), None)
        if successor:  # a door that holds a name now joined it after any record naming peer
            hint = f", its last door now holds @{successor}"
        elif old is not None and old["kind"] == "leave":
            hint = f", it left this bag at {display_stamp(old['at'])}"
        else:
            hint = ""
        fail(f"@{peer} is not registered{hint}, run {bag().command('read')}",
             recovery={"action": "read", "actor": "caller", "bag": bag().label})


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
        peers.add("codex")  # a codex session with an invalid concrete ID is refused at its door, never a terminal
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
    env = {k: v for k, v in os.environ.items() if k not in HIDDEN_FROM_CHILD}
    try:
        run = subprocess.run([codex, "queue", "--thread", door["thread"], "--message", text], env=env,
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


FOOTER = ("Reply only when a reply advances the task. Do not send courtesy acknowledgements or "
          "unsolicited delivery checks, and do not add a question or offer that needs no answer.")
FINAL = "Final letter. Do not reply to this letter, even if its body asks for a reply."


def envelope(rec, state):
    """The delivered text, as CONCEPT.md shows it: heading, roster when the bag holds more
    than two names, body, then how to answer. A final letter ends with FINAL and no command."""
    text = f"Letter {state.letters + 1} from @{rec['from']} to @{rec['to']} via postbag (bag {bag().label})."
    if len(state.peers) > 2:
        text += "\nRegistered names in this bag: " + ", ".join(f"@{p}" for p in sorted(state.peers)) + "."
    text += f"\n\n{rec['body']}\n\n"
    if rec.get("final"):
        return text + FINAL
    text += FOOTER + "\n"
    if bag().named or bag().label == "default":  # the MCP interface refuses path selectors
        text += (f"If you have Postbag MCP tools, call postbag_send with bag {bag().label} and to @{rec['from']}.\n"
                 "Otherwise reply with:\n")
    else:
        text += "If it needs an answer, reply with:\n"
    command = bag().command(f"send @{rec['from']} -")
    return text + (f"{command} <<'POSTBAG'\n<your reply>\nPOSTBAG\n"
                   "Change POSTBAG at both ends to a word that does not occur in your reply.")


# verbs ----------------------------------------------------------------------

def join(source, peer=None, *, wait=True):
    peer = name(source if peer is None else peer)
    if source not in inside():
        fail(f"join {source} from inside a {source} session")
    if peer in PEERS and peer != source:
        fail(f"@{peer} is reserved for {peer} doors")
    fields = current_door(source)
    with ledger(create=True, wait=wait) as write:
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


def send(to, body, *, final=False, wait=True):
    """Submit once; return receipt metadata without asserting recipient acceptance."""
    to = name(to, mention=True)
    if type(final) is not bool:
        fail("final must be true or false", error_code="invalid_input")
    if "\0" in body:
        fail("a letter cannot contain a NUL byte", error_code="invalid_input")
    if not body.strip():
        fail("a letter needs text", error_code="invalid_input")
    if not encodable(body):  # surrogateescape stdin under a C locale: no door or ledger can carry it
        fail("a letter must be valid Unicode text", error_code="invalid_input")
    submitted = None  # the letter, once its door took it: from then on a failure must not invite a resend
    try:
        with ledger(wait=wait) as write:
            state = Snapshot(records())
            sender = state.sender()
            if sender == to:
                fail(f"@{to} is your own name")
            target = state.target(to)
            fields = {"from": sender, "to": to, "body": body}
            if final:
                fields["final"] = True  # the record carries final only when it is true
            rec = record("letter", **fields)
            label = f"letter {state.letters + 1}"
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
                     error_code="transport_unavailable",
                     recovery={"action": "join", "actor": "recipient", "bag": bag().label,
                               "vendor": vendor(target), "name": to})
            submitted = label
            write(rec)
    except OSError as e:
        if submitted is None:
            raise
        # The write, its flush or its fsync failed: the record may be absent, partial, or in the
        # file without confirmed durability. Only the bag itself can say which.
        fail(f"{submitted} was submitted to @{to}'s door but its recording could not be confirmed ({e}), "
             f"do not resend before inspecting the bag and @{to}'s session",
             error_code="recording_failed", submission_state="submitted")
    print(f"{label} delivered to @{to} in bag {bag().label}")
    return {"bag": bag().label, "from": sender, "to": to, "record": rec["n"],
            "letter": state.letters + 1, "final": final, "submission_state": "submitted"}


def leave(*, wait=True):
    """Withdraw this door's registration from the selected bag. Nothing is created or contacted."""
    sources = sorted(inside())
    if not sources:
        fail("leave is a peer's verb, run it inside a claude or codex session")
    keys = {source: (source, *current_door(source).values()) for source in sources}
    with ledger(wait=wait, verb="leave") as write:
        state = Snapshot(records())
        held = state.held_by(keys.values(), "leave")
        if not held:  # never joined, already left, or its name was taken: read says which
            fail(f"this door holds no name in bag {bag().label}, run {bag().command('read')}",
                 recovery={"action": "read", "actor": "caller", "bag": bag().label})
        peer = held[0]
        door = state.peers[peer]
        source = vendor(door)
        rec = record("leave", peer=peer, vendor=source, **{field: door[field] for field in SESSION[source]})
        try:
            write(rec)
        except OSError as e:
            # The write, its flush or its fsync failed: the record may be absent, partial, or in the
            # file without confirmed durability. Only the bag itself can say which.
            fail(f"@{peer}'s leave could not be confirmed in bag {bag().label} ({e}), "
                 f"read the bag before leaving again", error_code="recording_failed",
                 recovery={"action": "read", "actor": "caller", "bag": bag().label})
    print(f"@{peer} ({source}) left bag {bag().label}")
    return {"bag": bag().label, "name": peer, "vendor": source, "record": rec["n"]}


def plural(count, noun):
    return f"{count} {noun}{'' if count == 1 else 's'}"


def read(count):
    state = Snapshot(records())
    names = ", ".join(f"@{peer} ({vendor(rec)})" for peer, rec in sorted(state.peers.items())) or "none"
    letters = plural(state.letters, "letter") if state.letters else "no letters"
    experimental = " Experimental: more than two peers." if len(state.peers) > 2 else ""
    print(f"in bag {bag().label}: {names}. {letters}.{experimental}")
    for rec, letter, note in state.history[-count:] if count else state.history:
        kind = rec["kind"]
        if kind == "letter":  # a letter's number in the bag stands where the other kinds print their name
            kind = f"{letter} final" if rec.get("final") else str(letter)
        line = f"{rec['n']:>4}  {display_stamp(rec['at'])}  {kind:<6}"
        if rec["kind"] == "letter":
            print(f"{line} @{rec['from']} -> @{rec['to']}")
            print("\n".join("      " + l for l in rec["body"].splitlines()))
        elif rec["kind"] == "open":
            print(f"{line} {rec['limit']} letters (history)")
        else:  # a join with its notes, or a leave with none
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
    summary = inventory_summary(counts, "  /  ")
    if summary:
        line(summary)
    now = datetime.now().astimezone()
    dated = [(row, *inventory_time(row[2], now)) for row in rows]
    dated.sort(key=lambda item: (item[2] is None, -(item[2] or 0), item[0][0]))
    entries = []
    for (label, letters, _, peers), when, _ in dated:
        if peers is None:
            people, when = "Unavailable", "Unknown"
        elif not peers:
            people = "No registered peers"
        else:
            people = "  /  ".join(
                f"{source.title()}: " + ", ".join(f"@{peer}" for peer, v in peers if v == source)
                for source in sorted({v for _, v in peers}))
        entries.append((label, "unavailable" if letters is None else str(letters), when, people))

    if entries:
        print()
    if entries and width >= 100:
        widths = [min(26, max(3, *(display_width(row[0]) for row in entries))),
                  min(12, max(7, *(len(row[1]) for row in entries))), 16]
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

        table_row(("Bag", "Letters", "Last letter", "Registered peers"), heading=True)
        print()
        for row in entries:
            table_row(row)
            if resumptions is not None:
                print_resumes(resumptions.get(row[0], []))
    else:
        for label, letters, when, people in entries:
            line(label, "1", words=False)
            held = plural(int(letters), "letter") if letters[0].isdigit() else letters
            line(f"{held}  |  Last letter: {when}", indent=2)
            line(people, indent=2)
            if resumptions is not None:
                print_resumes(resumptions.get(label, []))
            print()
    if entries and width >= 100:
        print()
    line("Local times. Registered does not mean running.")
    line("Scope: ~/.postbag + selected custom path if present. Other paths are not listed.")


def inventory_summary(counts, separator):
    """The nonzero counts, as `N with letters`, `N empty` and `N unavailable`."""
    return separator.join(f"{counts[key]} {label}" for key, label in (
        ("letters", "with letters"), ("empty", "empty"), ("unavailable", "unavailable")) if counts[key])


def inventory():
    """Return rows, counts, resume metadata and problems without printing or contacting doors.

    rows: one (label, letters, last, peers) per bag, where letters is the number of letters
    the bag holds, last the ISO stamp of the latest letter or "-", and peers the sorted
    (name, vendor) pairs held now. An unavailable bag has letters None and peers None.
    counts: bags with at least one letter, bags with none, and unavailable bags.
    """
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
    counts = dict(letters=0, empty=0, unavailable=0)
    for candidate in sorted(candidates.values(), key=lambda c: (c.label != "default", c.label)):
        token = _selection.set(candidate)
        try:
            state = Snapshot(records(wait=False, refuse_missing=False))
            counts["letters" if state.letters else "empty"] += 1
            last = next((datetime.fromisoformat(rec["at"]).isoformat()
                         for rec, *_ in reversed(state.history) if rec["kind"] == "letter"), "-")
            peers = [(peer, vendor(rec)) for peer, rec in sorted(state.peers.items())]
            rows.append((candidate.label, state.letters, last, peers))
            resumptions[candidate.label] = [
                (peer, session_id(rec.get("session_id")))
                for peer, rec in sorted(state.peers.items()) if vendor(rec) == "claude"]
        except (SystemExit, OSError, UnicodeError, ValueError, RecursionError) as e:
            counts["unavailable"] += 1
            rows.append((candidate.label, None, "-", None))
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
        summary = inventory_summary(counts, " / ")
        print(f"{total} {'bag' if total == 1 else 'bags'} found" + (f": {summary}." if summary else "."))
        table = [("Bag", "Letters", "Last letter", "Registered peers"),
                 *((label, "unavailable" if letters is None else str(letters), last, "-" if peers is None else
                    ", ".join(f"@{peer} ({source})" for peer, source in peers) or "none")
                   for label, letters, last, peers in rows)]
        widths = [max(len(row[i]) for row in table) for i in range(3)]
        for row in table:
            print(" | ".join([*(row[i].ljust(widths[i]) for i in range(3)), row[3]]))
            if resume:
                print_resumes(resumptions.get(row[0], []))
        print(f"Scope: default and named bags under {Bag('default').path.parent}, "
              "plus the selected custom path if present. Other custom paths are not listed.")
        print("Registrations do not show whether sessions are running.")
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
    s = sub.add_parser("send")
    s.add_argument("to", help="the recipient's name, with or without @")
    s.add_argument("body", help='the text, or "-" to read it from stdin')
    s.add_argument("--final", action="store_true", help="mark the letter as one that asks for no reply")
    sub.add_parser("read").add_argument("count", nargs="?", type=positive, help="only the last N records")
    b = sub.add_parser("bags", help="list local bags without contacting sessions",
                   description="List the default and named bags, plus an existing selected custom path.")
    b.add_argument("--resume", action="store_true", help="show Claude resume commands for conversations recorded at join")
    sub.add_parser("leave", help="withdraw this session's door from the bag until it joins again",
                   description="Inside a session: withdraw its registered name from the bag. The history stays.")
    sub.add_parser("mcp", help="start the optional MCP server on stdio, the same as postbag-mcp",
                   description="Start the MCP server that postbag-mcp starts. It takes no bag and no arguments. "
                               "Hosts that run a package by its own name, such as uvx, use this entry.")
    a = p.parse_args(argv)
    if a.verb == "mcp":
        serve_mcp(a)
        return
    try:
        _selection.set(bag())  # Freeze the environment's path before any I/O or delivery.
        run(a)
        sys.stdout.flush()
    except BrokenPipeError:
        # The reader closed early; also prevent another failure during exit's flush.
        with open(os.devnull, "w") as sink:
            os.dup2(sink.fileno(), sys.stdout.fileno())
    except (OSError, UnicodeError) as e:
        fail(f"{a.verb} failed ({e})")


def serve_mcp(a):
    """A launcher, not a ledger verb: refuse a bag selection, then hand stdio to the MCP server."""
    if a.bag is not None:
        fail("mcp takes no bag, each tool call names its own", context=False, error_code="invalid_input")
    try:
        import postbag_mcp
    except ImportError:  # a broken installation; a missing SDK is reported by serve() itself
        fail("the MCP module is not installed beside postbag, reinstall with: pip install 'postbag[mcp]'",
             context=False, error_code="invalid_input")
    postbag_mcp.serve()  # exits 2 with the same install hint as postbag-mcp when the SDK is missing


def run(a):
    if a.verb == "join":
        join(a.vendor, a.name)
    elif a.verb == "send":
        send(a.to, sys.stdin.read().rstrip("\n") if a.body == "-" else a.body, final=a.final)
    elif a.verb == "read":
        read(a.count)
    elif a.verb == "leave":
        leave()
    else:
        bags(a.resume)


if __name__ == "__main__":
    main()
