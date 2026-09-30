# Local MCP interface

The optional `postbag-mcp` command exposes four tools over stdio. It uses
the existing ledger and native delivery. It does not start agents, open
exchanges, replenish budgets, poll recipients, or retry letters.

## Install and connect

The MCP interface is unreleased. From this checkout:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install '.[mcp]'
.venv/bin/postbag-mcp --version
```

The extra installs MCP Python SDK 2.2 or later within major version 2.
Installing Postbag without the extra keeps the CLI free of runtime
dependencies. `postbag-mcp` then explains which extra is missing.

Use the absolute executable path in each host's configuration. For Codex:

```toml
[mcp_servers.postbag]
command = "/absolute/path/to/.venv/bin/postbag-mcp"
tool_timeout_sec = 60
```

For Claude Code:

```sh
claude mcp add --transport stdio postbag -- /absolute/path/to/.venv/bin/postbag-mcp
```

Restart or reconnect the MCP server after changing its configuration or
upgrading Postbag. Do not configure session IDs, socket paths, or tokens by
hand. Keep the host's normal permission prompts and native inbound policy.

The human opens a named bag from a terminal outside agent sessions:

```sh
/absolute/path/to/.venv/bin/postbag --bag review open --limit 6
```

Ask each agent to call `postbag_join` with `bag="review"` and a distinct
`name`. It can then call `postbag_send` with `bag="review"`, `to="peer-name"`,
and the letter's `body`. Both sessions should use the same Postbag version.
Existing CLI participants can join the same exchange. The native envelope
still includes a CLI reply command for recipients that do not have MCP tools.
MCP-enabled recipients should answer with `postbag_send`, using the envelope's
bag and sender. CLI participants need the same version's `postbag` executable
on their shell's `PATH`; configuring an absolute MCP command alone does not
put it there. For a checkout installation, launch those sessions with the
venv's `bin` directory prepended to `PATH`.

## Tools

| Tool | Arguments | Effect |
|---|---|---|
| `postbag_join` | `name`, `bag="default"` | Register this caller's native door. A reused name takes over its previous holder. |
| `postbag_send` | `to`, `body`, `bag="default"` | Submit one letter and record it against the shared budget. |
| `postbag_read` | `bag="default"`, `limit=20`, `before=null` | Return recent records in chronological order. Pass `next_before` as `before` for older records. |
| `postbag_bags` | `limit=50`, `offset=0` | Inventory default and named bags. Pass `next_offset` as `offset` for another page. |

Page limits range from 1 to 100. `before` is an exclusive ledger record
number. Send bodies must contain 1 to 65,536 UTF-8 bytes and no NUL bytes.
Bag and peer names are a lowercase letter followed by up to 15 lowercase
letters, digits, or hyphens. `to` also accepts an initial `@`.

MCP selects bags only by name and ignores `POSTBAG_LEDGER`. Absolute paths
remain a CLI feature. Read and inventory calls create no files and probe no
sessions. Endpoint credentials and conversation IDs are excluded from their
results. Letter bodies are shared content, so read access still reveals the
correspondence. Inventory preserves readable rows when another bag is busy
or corrupt and reports `inventory_incomplete` with those rows.

## Caller identity

There is no sender, vendor, thread ID, socket, or token tool argument.
Unknown arguments are refused. Identity comes from the trusted local host:

- **Codex:** the host supplies `_meta.threadId` on each tool call. Postbag
  requires that concrete thread ID for join and send. It ignores startup
  `CODEX_SESSION_ID` and per-call `sessionId`, which can refer to a shared
  root session. The CLI prefers `CODEX_THREAD_ID`, with the old variable as
  a fallback when it is absent. Rejoin after upgrading if a previous join
  recorded the shared root instead of the concrete thread.
- **Claude Code:** the MCP child inherits the process inbox socket and token.
  Postbag uses that pair. It omits `CLAUDE_CODE_SESSION_ID` when recording an
  MCP join because `/clear` can change the conversation without restarting
  the MCP process. Use a fresh CLI join if a current `bags --resume` hint is
  needed.
- A complete Claude inbox combined with a Codex `threadId`, invalid metadata,
  or missing identity refuses join and send. Read and inventory remain usable.

This is session routing, not authentication against other local processes.
A client that can launch this server can supply metadata, just as a local
process can set the CLI's environment. Use the supported trusted hosts.
Codex child agents need distinct peer names because they have distinct thread
IDs. Reusing the parent's name takes it over. The join receipt reports
`renamed` and `took`, including the previous vendor and join time, so a
takeover is visible without exposing its credentials.
Distinct names do not establish reachability: the native queue rejects some
spawned subagents, including unloaded spawned threads and loaded threads
using the newer multi-agent mode. Use the host's native orchestration for
those targets. [Queue restriction in 0.157.1](https://github.com/openai/codex/blob/rust-v0.157.1/codex-rs/app-server/src/request_processors/thread_queue_processor.rs#L292-L309).
Claude subagents sharing the same inbox act as the same peer. Postbag
does not create or supervise either kind of agent. A registered peer is not
evidence that its session is still running.

## Results and uncertain submissions

Application outcomes contain `ok`, `error_code`, `submission_state`, `message`,
and `data`, both as structured content and JSON text. Refusals set MCP
`isError`. Input schema failures use the SDK's standard MCP error result.

| `submission_state` | Meaning |
|---|---|
| `not_submitted` | This attempt did not submit a letter. Correct the reported problem before continuing. |
| `submitted` | The native transport returned successfully. Check `ok` to learn whether ledger recording also succeeded. This does not prove acceptance, reading, or execution. |
| `unknown` | Submission may have happened. Check the bag and recipient before considering another send. |
| `null` | The result is not a letter submission outcome. |

Successful sends include the sender, recipient, exchange, record and letter
numbers, and remaining budget. A ledger recording failure after successful
transport reports `recording_failed` and `submitted`. A native timeout,
partial socket write, nonzero queue exit, or worker crash can report
`unknown`. An empty ledger tail cannot establish that a letter was not sent.

Each call runs the installed module by absolute path in a fresh subprocess,
with private stdin and captured stdout and stderr. Worker imports ignore
the host project's directory and Python environment overrides. Output uses
ASCII JSON framing independent of the host locale. CLI globals and environment
cannot cross requests. MCP mutations
use a nonblocking exclusive ledger lock. A busy ledger reports `ledger_busy`
before native submission, so it cannot wait silently and send later.

Cancelling a request does not cancel its worker while the server remains
alive. Graceful server shutdown waits for workers to finish and record.
A client can still forcibly terminate the server and its children. A timeout,
disconnect, forced shutdown, or lost response must therefore be treated as
an unknown outcome. Never retry automatically.

## Verification

`test_mcp.py` uses the real SDK and stdio subprocesses with isolated homes,
fake native executables, and private Unix sockets. It covers current and
legacy protocol clients, concurrent sends, budget exhaustion, independent
bags, identity changes, missing metadata, secret redaction, malformed inputs,
pagination, native failures, and cancellation after a transport side effect.

Run the suite with:

```sh
.venv/bin/python -m pip install '.[dev,mcp]'
.venv/bin/python -m pytest -q
```

Native runtime evidence and remaining limits are recorded in
[native-compatibility.md](native-compatibility.md). Linux fixture tests do
not establish native vendor acceptance on Linux. Windows is unsupported.
