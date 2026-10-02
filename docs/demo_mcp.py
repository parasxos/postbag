"""Render the README demo: scripted calls to two real postbag MCP servers.

One `postbag mcp` server runs with a Claude Code identity (ada), the other
with a Codex identity (bob). Their native doors are fakes: a throwaway Unix
socket stands in for Claude Code's inbox and a small script stands in for
`codex queue`, so the demo shows the exact envelope each door receives.
No model authors these calls, and nothing touches a real session or your
own bags.

    vhs docs/demo.tape          # records docs/assets/demo.gif
    python docs/demo_mcp.py     # the same transcript in your terminal
"""
import json
import os
import pathlib
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
THREAD = "019a0000-0000-7000-8000-00000000b0b0"  # bob's Codex thread, fixed for a stable recording
DEADLINE = 30

ADA, BOB, DIM, BOLD, OK, END = "\033[38;5;215m", "\033[38;5;114m", "\033[2m", "\033[1m", "\033[38;5;151m", "\033[0m"


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
    """Fake native doors that keep what each recipient would be handed."""

    def __init__(self, temp):
        self.to_ada, self.to_bob = [], []
        self.socket_path = str(temp / "ada.sock")
        self.queue_log = temp / "bob.jsonl"
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
                    self.to_ada.append(message["message"]["content"])

    def wait(self, inbox, count):
        for _ in range(DEADLINE * 20):
            if inbox is self.to_bob and self.queue_log.exists():
                self.to_bob[:] = [json.loads(line) for line in self.queue_log.read_text().splitlines()]
            if len(inbox) >= count:
                return inbox[count - 1]
            time.sleep(0.05)
        raise TimeoutError("a submitted letter never reached its fake door")


def pause(seconds):
    sys.stdout.flush()
    time.sleep(seconds)


def show_call(who, colour, tool, **arguments):
    shown = "  ".join(f"{key}={json.dumps(value)}" for key, value in arguments.items())
    sys.stdout.write(f"{colour}{who:<19}{END}")
    for char in f"{BOLD}{tool}{END}  {shown}":
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(0.012)
    sys.stdout.write("\n")


def show_result(text):
    print(f"{' ' * 19}{OK}✓ {text}{END}")


def show_envelope(who, colour, envelope, keep):
    print(f"{colour}envelope captured at {who}'s door:{END}")
    lines = envelope.splitlines()
    for line in lines[:keep]:
        line = line if len(line) <= 92 else line[:91] + "…"
        print(f"{DIM}  │ {line}{END}" if line else f"{DIM}  │{END}")
    if len(lines) > keep:
        print(f"{DIM}  │ …{END}")


def first_sentence(outcome):
    return outcome["message"].split(". ")[0].rstrip(".")


def transcript(ada, bob, doors):
    print("\033[2J\033[H", end="")
    print(f"{DIM}postbag demo: scripted calls to two real postbag MCP servers, one with a Codex identity")
    print(f"(bob) and one with a Claude Code identity (ada). The native doors are fakes.{END}\n")
    pause(1.2)
    # The recipient joins first, so the first letter never meets an unregistered name.
    show_call("bob  Codex", BOB, "postbag_join", bag="review", name="bob")
    show_result(first_sentence(bob.call("postbag_join", bag="review", name="bob")))
    pause(0.8)
    show_call("ada  Claude Code", ADA, "postbag_join", bag="review", name="ada")
    show_result(first_sentence(ada.call("postbag_join", bag="review", name="ada")))
    pause(0.8)
    ask = "Review parser.py, top three findings please."
    show_call("ada  Claude Code", ADA, "postbag_send", bag="review", to="bob", body=ask)
    show_result(first_sentence(ada.call("postbag_send", bag="review", to="bob", body=ask)))
    pause(0.6)
    show_envelope("bob", BOB, doors.wait(doors.to_bob, 1), keep=6)
    pause(2.4)
    answer = "Empty input, swallowed date errors, no field bound."
    show_call("bob  Codex", BOB, "postbag_send", bag="review", to="ada", body=answer)
    show_result(first_sentence(bob.call("postbag_send", bag="review", to="ada", body=answer)))
    pause(0.6)
    show_envelope("ada", ADA, doors.wait(doors.to_ada, 1), keep=3)
    pause(1.8)
    done = "Fixed all three, merging."
    show_call("ada  Claude Code", ADA, "postbag_send", bag="review", to="bob", final=True, body=done)
    show_result(first_sentence(ada.call("postbag_send", bag="review", to="bob", final=True, body=done)))
    pause(0.6)
    show_envelope("bob", BOB, doors.wait(doors.to_bob, 2), keep=5)
    pause(2.4)
    show_call("bob  Codex", BOB, "postbag_leave", bag="review")
    show_result(first_sentence(bob.call("postbag_leave", bag="review")))
    pause(0.8)
    show_call("ada  Claude Code", ADA, "postbag_read", bag="review", limit=3)
    state = ada.call("postbag_read", bag="review", limit=3)["data"]
    peers = ", ".join(f"@{peer['name']} ({peer['vendor']})" for peer in state["peers"])
    show_result(f"{state['letters']} letters, registered now: {peers}")
    pause(4)


def main():
    with tempfile.TemporaryDirectory(prefix="postbag-demo-") as temp:
        temp = pathlib.Path(temp)
        home = temp / "home"
        home.mkdir()
        doors = Doors(temp)
        base = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "POSTBAG_CODEX": str(doors.queue), "PYTHONPATH": str(ROOT)}
        servers = []
        try:
            bob = Server(base, temp / "bob.stderr", meta={"threadId": THREAD})
            servers.append(bob)
            ada = Server({**base, "CLAUDECODE": "1", "CLAUDE_CODE_MESSAGING_SOCKET": doors.socket_path,
                          "CLAUDE_CODE_MESSAGING_TOKEN": "demo-token"}, temp / "ada.stderr")
            servers.append(ada)
            transcript(ada, bob, doors)
        except BaseException:
            for server in servers:
                sys.stderr.write(server.errors.read_text())
            raise
        finally:
            for server in servers:
                server.close()


if __name__ == "__main__":
    main()
