"""Optional local MCP tools. The ledger and native transports remain in postbag.

Run ``postbag-mcp`` after installing ``postbag[mcp]``. Each call uses a fresh
stdlib-only worker: CLI globals, environment and output cannot cross requests.
"""

import argparse
import asyncio
import contextlib
import io
import json
import os
import subprocess
import sys
from typing import Any

import postbag


MAX_BODY_BYTES = 65536
MAX_RESULT_DEPTH = 64
WORKER_PROTOCOL = 2
SESSION_VARS = {v for fields in postbag.SESSION.values() for v in fields.values()} | {
    "CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDECODE",
}


def result(ok: bool, message: str, *, data: dict | None = None,
           error_code: str | None = None, submission_state: str | None = None) -> dict:
    return {"ok": ok, "error_code": error_code, "submission_state": submission_state,
            "message": message, "data": data or {}}


def refusal(message: str, code: str = "invalid_input", state: str | None = "not_submitted") -> dict:
    return result(False, message + "; stop and ask the human", error_code=code,
                  submission_state=state)


def valid_worker_result(payload: Any, operation: str) -> bool:
    """Keep malformed worker output inside the structured outcome contract."""
    if not isinstance(payload, dict) or set(payload) != {
        "ok", "error_code", "submission_state", "message", "data",
    }:
        return False
    ok, code, state = payload["ok"], payload["error_code"], payload["submission_state"]
    if not isinstance(ok, bool) or not isinstance(payload["message"], str) or not isinstance(payload["data"], dict):
        return False
    if (ok and code is not None) or (not ok and (not isinstance(code, str) or not code)):
        return False
    if state is not None and (not isinstance(state, str) or state not in {"not_submitted", "unknown", "submitted"}):
        return False
    if operation == "send" and (state is None or (ok and state != "submitted")):
        return False
    pending = [(payload, 0)]
    while pending:
        container, depth = pending.pop()
        if depth > MAX_RESULT_DEPTH:
            return False
        values = container.values() if isinstance(container, dict) else container
        pending.extend((value, depth + 1) for value in values if isinstance(value, (dict, list)))
    try:
        # json.loads accepts non-finite numbers and escaped lone surrogates.
        # Neither can cross the MCP boundary as interoperable JSON text.
        json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, UnicodeError, RecursionError):
        return False
    return True


def refusal_result(exc: postbag.Refusal) -> dict:
    """Use core recovery metadata to give MCP callers tool-specific guidance."""
    recovery = getattr(exc, "recovery", None)
    message = str(exc)
    if isinstance(recovery, dict):
        action, actor = recovery.get("action"), recovery.get("actor")
        peer, vendor = recovery.get("name"), recovery.get("vendor")
        allowed = {("join", "caller"), ("join", "recipient"), ("read", "caller"), ("bags", "caller")}
        if (not isinstance(action, str) or not isinstance(actor, str) or (action, actor) not in allowed
                or not postbag.valid_name(recovery.get("bag"))
                or set(recovery) - {"action", "actor", "bag", "name", "vendor"}
                or (peer is not None and not postbag.valid_name(peer))
                or (vendor is not None and (not isinstance(vendor, str) or vendor not in postbag.PEERS))
                or (actor == "recipient" and (peer is None or vendor is None))):
            recovery = None
    else:
        recovery = None
    if recovery:
        selected = json.dumps(recovery.get("bag"))
        if action == "join" and actor in {"caller", "recipient"}:
            instruction = (f"call postbag_join with bag={selected} and name={json.dumps(peer)}"
                           if peer else f"choose an available peer name and call postbag_join with bag={selected} and that name")
            if actor == "recipient":
                message = (f"@{peer}'s door did not answer. If its session restarted, have that recipient "
                           f"{instruction} from its own session. A recipient without MCP tools can use "
                           f"{postbag.bag().command('join ' + vendor + ' ' + peer)}.")
            else:
                reason = message.removeprefix(f"postbag: in bag {recovery['bag']}: ")
                reason = reason.removesuffix("; stop and ask the human").rstrip(".")
                message = f"{reason}. To register, {instruction}."
        elif action == "read" and actor == "caller":
            if exc.error_code == "ledger_busy":
                message = ("The bag is busy. Wait for its current operation to finish, then "
                           f"call postbag_read with bag={selected}. Do not resend a pending letter.")
            else:
                message = ("The requested peer is not currently registered in this bag. "
                           f"Call postbag_read with bag={selected} to inspect the registered names.")
        elif action == "bags" and actor == "caller":
            message = (f"Bag {selected} does not exist. "
                       "Call postbag_bags to inspect the available bags.")
        message = message.rstrip(".") + "; stop and ask the human"
    return result(False, message, data={"recovery": recovery} if recovery else None,
                  error_code=exc.error_code, submission_state=exc.submission_state)


def caller_environment(meta: dict, startup: dict) -> tuple[str, dict]:
    """Resolve host-authored metadata, never a model-supplied sender argument.

    Codex supplies threadId per call; sessionId can identify an entire agent tree.
    Claude's inbox belongs to the process, while its conversation ID can change
    after /clear. Do not copy the child's frozen conversation ID into the ledger.
    """
    claude = bool(startup.get("CLAUDE_CODE_MESSAGING_SOCKET")
                  and startup.get("CLAUDE_CODE_MESSAGING_TOKEN"))
    if "threadId" in meta:
        thread = postbag.session_id(meta["threadId"])
        if not thread or claude:
            raise ValueError("caller identity is invalid or ambiguous")
        source, identity = "codex", {"CODEX_THREAD_ID": thread, "CODEX_SESSION_ID": thread}
    elif claude and (startup.get("CLAUDECODE") == "1" or startup.get("CLAUDE_CODE_SESSION_ID")):
        source = "claude"
        identity = {key: startup[key] for key in postbag.SESSION[source].values()}
    else:
        raise ValueError("caller identity is unavailable; reconnect Postbag in a supported Codex or Claude session")
    env = {key: value for key, value in startup.items()
           if key not in SESSION_VARS and key != "POSTBAG_LEDGER"}
    env.update(identity)
    return source, env


def public_peers(state: Any) -> list[dict]:
    return [{"name": name, "vendor": postbag.vendor(rec)}
            for name, rec in sorted(state.peers.items())]


def read_data(limit: int, before: int | None) -> dict:
    state = postbag.Snapshot(postbag.records(wait=False))
    history = [item for item in state.history if before is None or item[0]["n"] < before]
    chosen = history[-limit:]
    records = []
    for rec, number, _ in chosen:
        public = {"n": rec["n"], "at": postbag.display_stamp(rec["at"]),
                  "kind": rec["kind"]}
        if rec["kind"] == "join":
            public.update(peer=rec["peer"], vendor=postbag.vendor(rec))
        elif rec["kind"] == "open":
            public["limit"] = rec["limit"]
        else:
            rec["body"].encode("utf-8")  # reject malformed Unicode before returning structured content
            public.update({key: rec[key] for key in ("from", "to", "body")})
            public["letter"] = number
            public["final"] = rec.get("final", False)
        records.append(public)
    return {"bag": postbag.bag().label, "letters": state.letters,
            "peers": public_peers(state), "records": records,
            "next_before": chosen[0][0]["n"] if len(history) > len(chosen) else None}


def worker(request: dict) -> dict:
    """One invocation in a child process; no MCP dependency is imported here."""
    operation, args = request["operation"], request["arguments"]
    selected = args.get("bag", "default")
    if not postbag.valid_name(selected):
        return refusal("MCP bags must be names, not filesystem paths")
    token = postbag._selection.set(postbag.Bag(selected))
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(io.StringIO()):
            if operation == "join":
                receipt = postbag.join(request["vendor"], args["name"], wait=False)
                return result(True, captured.getvalue().strip(), data=receipt)
            if operation == "send":
                final = args.get("final", False)
                if type(final) is not bool:
                    return refusal("final must be a boolean")
                try:
                    encoded = args["body"].encode("utf-8")
                except UnicodeEncodeError:
                    return refusal("a letter must contain valid Unicode text")
                if len(encoded) > MAX_BODY_BYTES:
                    return refusal("letter exceeds 65536 UTF-8 bytes; shorten it")
                receipt = postbag.send(args["to"], args["body"], final=final, wait=False)
                message = (f"Letter {receipt['letter']} submitted to @{receipt['to']}. "
                           "Acceptance and execution are unconfirmed. "
                           "Do not resend it or send a delivery check.")
                if final:
                    message += " Marked final, requesting no reply."
                return result(True, message, data=receipt, submission_state="submitted")
            if operation == "read":
                return result(True, "Registered peers are not proof of live sessions. Letter records show submissions.",
                              data=read_data(args["limit"], args.get("before")))
            if operation == "bags":
                rows, _, _, problems = postbag.inventory()
                offset, limit = args["offset"], args["limit"]
                items = [{"bag": label, "letters": letters, "last_letter": None if last == "-" else last,
                          "peers": None if peers is None else
                          [{"name": name, "vendor": vendor} for name, vendor in peers]}
                         for label, letters, last, peers in rows[offset:offset + limit]]
                data = {"version": postbag.__version__, "bags": items, "total": len(rows), "offset": offset,
                        "next_offset": offset + limit if offset + limit < len(rows) else None,
                        "errors": problems, "scope": "Default and named bags under ~/.postbag; custom paths excluded."}
                return result(not problems, "Inventory incomplete." if problems else
                              "Registered does not mean running.", data=data,
                              error_code="inventory_incomplete" if problems else None)
            return refusal("unknown operation")
    except postbag.Refusal as exc:
        return refusal_result(exc)
    except BlockingIOError:
        if operation == "send":
            return refusal("unexpected send failure; read the bag and check the recipient before resending",
                           "operation_failed", "unknown")
        return result(False, "An operation is in progress in this bag. Wait for it to finish before reading again. "
                      "Do not resend a pending letter.", error_code="ledger_busy")
    except (OSError, UnicodeError, ValueError, RecursionError):
        # Unexpected send failures cannot establish whether native submission happened.
        return refusal("cannot complete the operation; inspect the bag before retrying",
                       "operation_failed", "unknown" if operation == "send" else "not_submitted")
    except SystemExit:
        return refusal("operation refused; inspect the bag", "refused",
                       "unknown" if operation == "send" else "not_submitted")
    finally:
        postbag._selection.reset(token)


class Workers:
    """Cancellation detaches a caller, never terminates an in-flight send.

    Track the communicate task so the pipe is drained and the child is reaped.
    Graceful server shutdown waits for active workers to finish recording.
    """

    def __init__(self, startup: dict):
        self.startup = startup
        self.pending: set[asyncio.Task] = set()

    async def call(self, operation: str, arguments: dict, meta: dict) -> dict:
        env = {key: value for key, value in self.startup.items()
               if key not in SESSION_VARS and key != "POSTBAG_LEDGER"}
        vendor = None
        if operation in {"join", "send"}:
            try:
                vendor, env = caller_environment(meta, self.startup)
            except ValueError as exc:
                return refusal(str(exc), "identity_unavailable", "not_submitted" if operation == "send" else None)
        request = {"operation": operation, "arguments": arguments, "vendor": vendor}
        task = asyncio.create_task(self._run(request, env))
        self.pending.add(task)
        task.add_done_callback(self.pending.discard)
        return await asyncio.shield(task)

    async def _run(self, request: dict, env: dict) -> dict:
        # Popen has no asyncio transport that might kill a child on cancellation
        # or event-loop teardown. The thread drains its pipes and reaps it.
        return await asyncio.to_thread(self._run_sync, request, env)

    def _run_sync(self, request: dict, env: dict) -> dict:
        operation = request["operation"]
        module = os.path.realpath(__file__)
        try:
            process = subprocess.Popen(
                [sys.executable, "-E", "-s", module, f"--worker-v{WORKER_PROTOCOL}"],
                cwd=os.path.dirname(module), start_new_session=True,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        except OSError:
            return refusal("cannot start a Postbag worker", "worker_unavailable")
        try:
            with process:
                output, _ = process.communicate(json.dumps(request).encode("utf-8"))
        except OSError:
            output = b""
        try:
            payload = json.loads(output) if process.returncode == 0 else None
            if valid_worker_result(payload, operation):
                return payload
        except (ValueError, UnicodeError, RecursionError):
            pass
        return refusal("worker stopped without a valid result. If Postbag was upgraded or downgraded, "
                       "reconnect its MCP server. Read the bag and check the recipient before resending",
                       "worker_failed", "unknown" if operation == "send" else "not_submitted")

    async def close(self) -> None:
        if self.pending:
            await asyncio.gather(*tuple(self.pending), return_exceptions=True)


def create_server():
    """Import the optional SDK only when serving MCP."""
    from typing import Annotated, Literal

    from anyio import CancelScope
    from mcp.server import MCPServer
    from mcp.server.mcpserver import Context
    from mcp.types import CallToolResult, TextContent, ToolAnnotations
    from pydantic import BaseModel, ConfigDict, Field

    class Outcome(BaseModel):
        model_config = ConfigDict(extra="forbid")
        ok: bool
        error_code: str | None
        submission_state: Literal["not_submitted", "unknown", "submitted"] | None
        message: str
        data: dict[str, Any]

    workers = Workers(dict(os.environ))

    @contextlib.asynccontextmanager
    async def lifespan(server):
        try:
            yield workers
        finally:
            # MCP's task group cancels on EOF. Shield the drain from that scope.
            with CancelScope(shield=True):
                await workers.close()

    server = MCPServer(
        "postbag", version=postbag.__version__, lifespan=lifespan,
        instructions=("Postbag carries letters between existing sessions and records submitted letters. "
                      "Joining creates the selected bag if it does not exist. "
                      "Independent native sessions join under distinct names. "
                      "Claude subagents sharing an inbox use the parent's peer. Joining another name renames it. "
                      "Send only when authorized to collaborate. "
                      "Reply only when a reply advances the task. Do not reply to a final letter, "
                      "even if its body asks for a reply. When replying, use postbag_send with the "
                      "letter's bag and sender, even when its envelope includes a CLI reply command. "
                      "No courtesy acknowledgements or unsolicited delivery checks. "
                      "Do not add a question or offer that needs no answer. "
                      "Submission is not acceptance or completion. "
                      "If send is cancelled, times out, or returns an unknown outcome, read the bag and "
                      "check the recipient before resending. Never retry automatically."))

    def wire(payload: dict) -> CallToolResult:
        validated = Outcome.model_validate(payload).model_dump()
        # Text includes data so clients without structured-content support remain useful.
        return CallToolResult(content=[TextContent(text=json.dumps(validated, ensure_ascii=False))],
                              structured_content=validated, is_error=not validated["ok"])

    async def invoke(operation: str, arguments: dict, ctx: Context) -> CallToolResult:
        raw = (ctx.request_context.params or {}).get("arguments", {})
        if set(raw) - set(arguments):
            payload = refusal("unknown tool arguments are not accepted")
        else:
            payload = await workers.call(operation, arguments, dict(ctx.request_context.meta or {}))
        if operation != "send":
            payload["submission_state"] = None
        return wire(payload)

    BagName = Annotated[str, Field(strict=True, pattern=r"^[a-z][a-z0-9-]{0,15}$",
                                   description="Default or named bag. Join creates a missing bag.")]
    Name = Annotated[str, Field(strict=True, pattern=r"^[a-z][a-z0-9-]{0,15}$")]
    Output = Annotated[CallToolResult, Outcome]
    read_only = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True,
                                open_world_hint=False)

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True,
                                           idempotent_hint=False, open_world_hint=False))
    async def postbag_join(name: Name, ctx: Context, bag: BagName = "default") -> Output:
        """Register this caller's native session under a name. Reusing a name takes it over.

        Claude subagents sharing an inbox are the same peer. Joining another name
        renames the parent's peer. Use the existing peer without joining again. Independent
        native sessions need distinct names.
        Creates the bag if missing. Identity comes from the host, never tool arguments.
        Claude MCP joins omit resume metadata because /clear can change its conversation.
        """
        return await invoke("join", {"name": name, "bag": bag}, ctx)

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False,
                                           idempotent_hint=False, open_world_hint=True))
    async def postbag_send(
        to: Annotated[str, Field(strict=True, pattern=r"^@?[a-z][a-z0-9-]{0,15}$")],
        body: Annotated[str, Field(strict=True, min_length=1, max_length=MAX_BODY_BYTES,
                                   description="Letter text, at most 65536 UTF-8 bytes. No NUL bytes.")],
        ctx: Context, bag: BagName = "default",
        final: Annotated[bool, Field(strict=True, description="Ask the recipient not to reply to this letter.")] = False,
    ) -> Output:
        """Submit one letter to a registered peer and record it in the bag.

        final=true asks for no reply. It is guidance, and later letters remain allowed.
        Requires prior join. Never retry an unknown outcome, cancelled call, or timeout
        before reading the bag and checking the recipient. Does not confirm execution.
        """
        return await invoke("send", {"to": to, "body": body, "bag": bag, "final": final}, ctx)

    @server.tool(annotations=read_only)
    async def postbag_read(
        ctx: Context, bag: BagName = "default",
        limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 20,
        before: Annotated[int | None, Field(strict=True, ge=1)] = None,
    ) -> Output:
        """Read recent records in chronological order, excluding endpoint credentials.

        Pass next_before as before to page backward by ledger record number. The letters
        count covers the whole bag. Peer registration is not liveness.
        """
        return await invoke("read", {"bag": bag, "limit": limit, "before": before}, ctx)

    @server.tool(annotations=read_only)
    async def postbag_bags(
        ctx: Context, limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 50,
        offset: Annotated[int, Field(strict=True, ge=0)] = 0,
    ) -> Output:
        """Inventory default and named bags, letter counts, and peers without probing sessions.

        Excludes letter bodies, credentials, and custom ledger paths. Errors preserve
        readable rows. Pagination can shift if bags are added or removed between calls.
        """
        return await invoke("bags", {"limit": limit, "offset": offset}, ctx)

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Postbag local MCP tools over stdio")
    parser.add_argument("--version", action="version", version=f"postbag-mcp {postbag.__version__}")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    modes.add_argument(f"--worker-v{WORKER_PROTOCOL}", dest="worker_current",
                       action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker or args.worker_current:
        if args.worker:
            # A running 1.x parent must never dispatch into new worker semantics.
            # Keep its result shape and exit 0 so that parent preserves the refusal.
            response = refusal("The running MCP server and installed worker use different protocols. "
                               "Reconnect Postbag in this host before using its tools",
                               "worker_version_mismatch")
        else:
            try:
                response = worker(json.load(sys.stdin))
            except Exception:
                response = refusal("worker failed; inspect the bag before resending", "worker_failed", "unknown")
        # ASCII framing works even when -E ignores a host's UTF-8 overrides.
        sys.stdout.buffer.write(json.dumps(response).encode("ascii") + b"\n")
        return
    try:
        server = create_server()
    except ImportError:
        parser.exit(2, "Install MCP support with: pip install 'postbag[mcp]'\n")
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
