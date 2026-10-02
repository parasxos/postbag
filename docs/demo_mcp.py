"""Render the README demo: scripted calls to two real postbag MCP servers.

Two panes, Claude Code on the left and Codex on the right. Each runs its own
`postbag mcp` server with that host's identity, shows its own tool calls, and
shows the letters its door receives. The doors are stand-ins: a throwaway Unix
socket for Claude Code's inbox and a small script for `codex queue`, so the demo
shows the exact envelope each side would be handed. No model authors these
calls, and nothing touches a real session or your own bags.

    vhs docs/demo.tape          # records docs/assets/demo.gif
    python docs/demo_mcp.py     # the same demo in a terminal of at least 100x28
"""
import json
import os
import pathlib
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
THREAD = "019a0000-0000-7000-8000-00000000b0b0"  # the Codex thread, fixed for a stable recording
DEADLINE = 30


class Server:
    """One agent's postbag MCP server, spoken to with plain JSON-RPC lines."""

    def __init__(self, env, errors, meta=None):
        self.meta = meta or {}
        self.next_id = 1
        self.errors = errors
        self.lines = queue.Queue()
        with errors.open("w") as sink:
            self.process = subprocess.Popen([sys.executable, str(ROOT / "postbag.py"), "mcp"], env=env,
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=sink, text=True)
        # A reader thread hands over complete lines, so each request waits on one deadline in total.
        self.reader = threading.Thread(target=self.read_lines, daemon=True)
        self.reader.start()
        try:
            self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                        "clientInfo": {"name": "postbag-demo", "version": "1"}})
            self.write({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except BaseException:
            self.close()
            sys.stderr.write(errors.read_text())
            raise

    def read_lines(self):
        for line in self.process.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def write(self, message):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def request(self, method, params):
        ident, self.next_id = self.next_id, self.next_id + 1
        self.write({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
        deadline = time.monotonic() + DEADLINE
        while True:
            try:
                line = self.lines.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                raise TimeoutError(f"no answer to {method} within {DEADLINE} s") from None
            if line is None:
                raise RuntimeError(f"the server exited during {method}")
            message = json.loads(line)
            if message.get("id") == ident:
                return message["result"]

    def call(self, tool, **arguments):
        result = self.request("tools/call", {"name": tool, "arguments": arguments, "_meta": self.meta})
        outcome = result["structuredContent"]
        # Only calls that really succeeded are shown; anything else stops the recording.
        if result.get("isError") or outcome["ok"] is not True:
            raise RuntimeError(f"{tool} failed: {outcome}")
        if tool == "postbag_send" and outcome["submission_state"] != "submitted":
            raise RuntimeError(f"{tool} was not submitted: {outcome}")
        return outcome

    def close(self):
        try:
            self.process.stdin.close()
        except OSError:
            pass  # the child already exited and closed its end
        try:
            self.process.wait(timeout=DEADLINE)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.reader.join(timeout=DEADLINE)
        self.process.stdout.close()


class Doors:
    """Fake native doors that keep what each recipient would be handed: an inbox socket for Claude Code, a queue script for Codex."""

    def __init__(self, temp):
        self.to_claude, self.to_codex = [], []
        self.socket_path = str(temp / "claude.sock")
        self.queue_log = temp / "codex.jsonl"
        self.queue = temp / "codex"
        self.queue.write_text(
            f"#!{sys.executable}\nimport json, sys\n"
            "args = sys.argv[1:]\n"
            f"with open({str(self.queue_log)!r}, 'a') as out:\n"
            "    out.write(json.dumps(args[args.index('--message') + 1]) + '\\n')\n")
        self.queue.chmod(0o700)
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(self.socket_path)
        listener.listen()
        threading.Thread(target=self.inbox, args=(listener,), daemon=True).start()

    def inbox(self, listener):
        while True:
            connection, _ = listener.accept()
            with connection:
                data = b""
                while chunk := connection.recv(65536):
                    data += chunk
            for line in data.decode().splitlines():
                message = json.loads(line)
                if message.get("type") == "user":
                    self.to_claude.append(message["message"]["content"])

    def wait(self, inbox, count):
        for _ in range(DEADLINE * 20):
            if inbox is self.to_codex and self.queue_log.exists():
                self.to_codex[:] = [json.loads(line) for line in self.queue_log.read_text().splitlines()]
            if len(inbox) >= count:
                return inbox[count - 1]
            time.sleep(0.05)
        raise TimeoutError("a submitted letter never reached its fake door")



W, G = 47, 6            # pane width and gutter, in columns: 100 columns in all
TOP, FOOT = 4, 27       # first content row, footer row
CSI = "\033["
END = CSI + "0m"
CLAUDE = CSI + "38;2;217;119;87m"   # coral
CODEX = CSI + "38;2;137;180;250m"   # blue
OK = CSI + "38;2;166;227;161m"      # green
DIM = CSI + "38;2;127;132;156m"     # grey
TEXT = CSI + "38;2;205;214;244m"    # body text
BOLD = CSI + "1m"


def at(row, col):
    return f"{CSI}{row};{col}H"


def flush(seconds=0.0):
    sys.stdout.flush()
    if seconds:
        time.sleep(seconds)


class Pane:
    def __init__(self, col, colour, title):
        self.col, self.colour, self.row = col, colour, TOP
        sys.stdout.write(at(1, col) + BOLD + colour + title + END + DIM + "  postbag MCP" + END)
        sys.stdout.write(at(2, col) + colour + "─" * W + END)

    def line(self, parts, typed=0.0):
        """Write one row of (style, text) parts at this pane's next row; typed>0 types it."""
        assert self.row < FOOT - 1, "pane overflow"
        assert sum(len(t) for _, t in parts) <= W, parts
        sys.stdout.write(at(self.row, self.col))
        for style, text in parts:
            sys.stdout.write(style)
            if typed:
                for char in text:
                    sys.stdout.write(char)
                    flush(typed)
            else:
                sys.stdout.write(text)
            sys.stdout.write(END)
        self.row += 1
        flush()

    def gap(self, rows=1):
        self.row += rows

    def call(self, tool, args, body=None, typed=0.010):
        """Show a tool call; return the row it started on (the arrow row for a send)."""
        start = self.row
        self.line([(BOLD + TEXT, tool), (TEXT, "  " + "  ".join(f"{k}={v}" for k, v in args))], typed)
        if body is not None:
            lines = body.splitlines()
            for i, text in enumerate(lines):
                q0, q1 = ('"' if i == 0 else " "), ('"' if i == len(lines) - 1 else "")
                self.line([(TEXT, f"  {q0}{text}{q1}")], typed)
        return start

    def ok(self, text):
        self.line([(OK, "✓ " + text)])


def excerpt(envelope, tail):
    """Verbatim lines of the delivered envelope: header split before 'via', body, then one tail line."""
    lines = envelope.splitlines()
    head = lines[0]
    cut = head.index(" via ")
    blank = [i for i, text in enumerate(lines) if text == ""]
    body = lines[blank[0] + 1: blank[1]]
    footer = lines[blank[1] + 1:]
    rows = [("head", head[:cut]), ("dim", head[cut + 1:])]
    rows += [("text", text) for text in body]
    if tail:
        line = next(text for text in footer if tail in text)
        line = line if line.startswith(tail) else "… " + line[line.index(tail):]
        rows += [("dim", part) for part in textwrap.wrap(line, 36 if line.startswith("…") else W - 2)]
    elif footer:
        rows.append(("dim", "…"))  # the elided reply instructions are marked, never silently dropped
    return rows


def arrive(pane, sender, rows, arrow_row, direction):
    """Draw the arrow on the sender's call row, then the letter box in the recipient pane."""
    gutter = W + 1  # first gutter column: panes start at 1 and W+G+1
    arrow = " ───▶ " if direction == ">" else " ◀─── "
    frames = [arrow[:i] for i in range(1, 7)] if direction == ">" else [arrow[-i:].rjust(6) for i in range(1, 7)]
    for frame in frames:
        sys.stdout.write(at(arrow_row, gutter) + sender.colour + frame + END)
        flush(0.04)
    pane.row = max(pane.row, arrow_row)
    styles = {"head": BOLD + sender.colour, "dim": DIM, "text": TEXT}
    for kind, text in rows:
        pane.line([(sender.colour, "▌ "), (styles[kind], text)])
        flush(0.06)


def transcript(claude_server, codex_server, doors):
    cols, rows = shutil.get_terminal_size()
    if cols < 2 * W + G or rows < FOOT + 1:
        raise SystemExit(f"demo needs {2 * W + G}x{FOOT + 1}, terminal is {cols}x{rows}")
    sys.stdout.write(CSI + "?25l" + CSI + "2J" + CSI + "H")
    left = Pane(1, CLAUDE, "Claude Code")
    right = Pane(W + G + 1, CODEX, "Codex")
    sys.stdout.write(at(FOOT, 1) + DIM + "Scripted tool calls to two real postbag MCP servers. "
                     "The native inputs are stand-ins." + END)
    flush(1.0)

    # Beat 1: both sessions join the same bag (the recipient's server is called first).
    left.call("postbag_join", [("bag", '"review"'), ("name", '"claude"')], typed=0.006)
    right.call("postbag_join", [("bag", '"review"'), ("name", '"codex"')], typed=0.006)
    codex_server.call("postbag_join", bag="review", name="codex")
    claude_server.call("postbag_join", bag="review", name="claude")
    left.ok("joined bag review")
    right.ok("joined bag review")
    left.gap(), right.gap()
    flush(0.8)

    # Beat 2: Claude Code asks Codex for a review; it lands in Codex as a user turn.
    ask = "Review my last commit. Top three issues?"
    row = left.call("postbag_send", [("to", '"codex"')], ask)
    claude_server.call("postbag_send", bag="review", to="codex", body=ask)
    left.ok("letter 1 submitted")
    flush(0.3)
    arrive(right, left, excerpt(doors.wait(doors.to_codex, 1), "call postbag_send"), row, ">")
    right.gap()
    flush(1.8)

    # Beat 3: Codex answers from its own session.
    answer = "1. empty input crashes parse()\n2. date errors are swallowed\n3. no size limit on fields"
    row = right.call("postbag_send", [("to", '"claude"')], answer, typed=0.007)
    codex_server.call("postbag_send", bag="review", to="claude", body=answer)
    right.ok("letter 2 submitted")
    flush(0.3)
    left.gap()
    arrive(left, right, excerpt(doors.wait(doors.to_claude, 1), None), row, "<")
    left.gap()
    flush(1.8)

    # Beat 4: Claude Code closes with a final letter.
    done = "Fixed all three. Merging."
    row = left.call("postbag_send", [("to", '"codex"'), ("final", "true")], done)
    claude_server.call("postbag_send", bag="review", to="codex", final=True, body=done)
    left.ok("letter 3 submitted")
    flush(0.3)
    right.gap()
    arrive(right, left, excerpt(doors.wait(doors.to_codex, 2), "Final letter"), row, ">")
    flush(1.2)

    # Beat 5: one shared record.
    left.gap()
    left.call("postbag_read", [("bag", '"review"')], typed=0.006)
    state = claude_server.call("postbag_read", bag="review", limit=3)["data"]
    names = " and ".join(f"@{p['name']}" for p in state["peers"])
    left.ok(f"{state['letters']} letters, {names} registered")
    sys.stdout.write(at(FOOT + 1, 1))
    flush(6)  # the tape stops recording during this hold, so no shell prompt is filmed


def main():
    with tempfile.TemporaryDirectory(prefix="postbag-demo-") as temp:
        temp = pathlib.Path(temp)
        home = temp / "home"
        home.mkdir()
        doors = Doors(temp)
        base = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "POSTBAG_CODEX": str(doors.queue), "PYTHONPATH": str(ROOT),
                "PYTHONDONTWRITEBYTECODE": "1"}
        servers = []
        try:
            codex = Server(base, temp / "codex.stderr", meta={"threadId": THREAD})
            servers.append(codex)
            claude = Server({**base, "CLAUDECODE": "1", "CLAUDE_CODE_MESSAGING_SOCKET": doors.socket_path,
                             "CLAUDE_CODE_MESSAGING_TOKEN": "demo-token"}, temp / "claude.stderr")
            servers.append(claude)
            transcript(claude, codex, doors)
        except BaseException:
            for server in servers:
                sys.stderr.write(server.errors.read_text())
            raise
        finally:
            sys.stdout.write(CSI + "?25h")
            for server in servers:
                server.close()


if __name__ == "__main__":
    main()
