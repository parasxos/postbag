# Local MCP interface

The optional `postbag-mcp` command exposes four tools over stdio. It uses
the same ledger and native delivery as the CLI. Joining creates a missing
bag. Postbag does not start agents, poll recipients, or retry letters.
Version 2.0 removes letter budgets, exchanges and the `open` command.

The installed 2.0 candidate `8b87b4f` passed the native acceptance gate and
the package checks described below. Historical checks describe their
recorded versions.

## Install and connect

Install both the CLI and MCP tools in one environment:

```sh
pipx install 'postbag[mcp]'
postbag --version
postbag-mcp --version
```

Alternatively, create a virtual environment and run
`python -m pip install 'postbag[mcp]'` inside it.

The extra installs MCP Python SDK 2.2 or later within major version 2.
Installing Postbag without the extra keeps the CLI free of runtime
dependencies. `postbag-mcp` then explains which extra is missing.

Use the absolute executable path in each host's configuration. For Codex:

```toml
[mcp_servers.postbag]
command = "/absolute/path/to/postbag-mcp"
tool_timeout_sec = 60
```

For Claude Code:

```sh
claude mcp add --transport stdio --scope user postbag -- /absolute/path/to/postbag-mcp
```

Restart or reconnect the MCP server after changing its configuration or
upgrading Postbag. Do not configure session IDs, socket paths, or tokens by
hand. Keep the host's normal permission prompts and native inbound policy.

If multiple Codex installations are present, set `POSTBAG_CODEX` in the MCP
server's environment to the executable belonging to the intended host.
This selects the native queue command, not the sender's identity. It avoids
shell `PATH` order selecting a different installed runtime. Use the same
setting for CLI participants when selecting that runtime is necessary.

MCP tools run in the server process, outside the agent's command sandbox.
A read-only command sandbox therefore does not prevent these tools from
writing the ledger or contacting a recipient. Hosts may approve MCP calls
automatically according to their tool settings. Postbag sets no limit on the
number or rate of letters. Use the host's tool-approval settings if each
letter should require confirmation. Approval gives a human an opportunity
to intervene, not a bound on the correspondence. The recipient keeps its own
permissions and inbound policy.

Ask each agent to call `postbag_join` with `bag="review"` and a distinct
`name`. The first valid join creates the bag. It can then call
`postbag_send` with `bag="review"`, `to="peer-name"`,
and the letter's `body`. Both sessions should use the same Postbag version.
Existing CLI participants can join the same bag. An ordinary native envelope
still includes a CLI reply command for recipients that do not have MCP tools.
MCP-enabled recipients should answer with `postbag_send`, using the envelope's
bag and sender. CLI participants need the same version's `postbag` executable
on their shell's `PATH`. Configuring an absolute MCP command alone does not
put it there. For a checkout installation, launch those sessions with the
venv's `bin` directory prepended to `PATH`.

## Upgrade existing sessions

Upgrade the installation that provides both commands. For a pipx-managed
installation, use `pipx upgrade postbag` if the MCP extra is already installed.
To add MCP to a CLI-only pipx installation, use
`pipx install --force 'postbag[mcp]'`. If `postbag` is a manual symlink to a
checkout, preserve that link before replacing it with the package installation.
Check `command -v postbag`, `postbag --version`, and `postbag-mcp --version`
in each session so CLI and MCP participants use the same version.

After installing or upgrading, restart or reconnect the host's MCP server.
A running server keeps its imported code until restarted. Sessions that do
not yet expose the new tools can keep using the upgraded CLI.

- In the ChatGPT desktop app, use **Settings > MCP servers**, save the
  configuration, then select **Restart**. This refreshes loaded threads on
  that app-server. Independently running app-servers need their own refresh.
  [Desktop setup](https://learn.chatgpt.com/docs/extend/mcp?surface=cli#configure-in-the-chatgpt-desktop-app).
- In a standalone Codex CLI session, finish the current turn, exit, and use
  `codex resume` to reopen the conversation with the new configuration.
  `/mcp` lists tools. It is not a reload command. Verify Postbag appears.
  If another client keeps that same thread loaded, its existing server
  configuration can persist. Refresh the owning server as well.
- In Claude Code, use `/mcp` and **Reconnect** if Postbag is listed. If the
  newly registered server is absent, exit and use `claude --resume` to
  reopen the conversation in a new process, then check `/mcp` again.
  [Reconnect](https://code.claude.com/docs/en/mcp#automatic-reconnection),
  [resume a session](https://code.claude.com/docs/en/sessions#resume-a-session).

Upgrade all CLI and MCP participants together for 2.0 and reconnect every
running MCP server. Existing bags and records are retained without rewriting.
Historical `open` rows keep their original `limit` field but have no effect
on 2.0 sends. There is no `open` command or remaining budget in 2.0.

Mixed 1.x and 2.0 participants are unsupported and are not negotiated or
rejected as a pair. A 1.x sender needs a retained `open` record and still
applies its budget, counting 2.0 letters against it. A 2.0 sender ignores
that budget. An older reader hides `final`. New bags have no `open` record,
so 1.x senders refuse there. The 1.4 CLI can create an empty default or
path-selected ledger during a refused send. Its read of a missing default
or path-selected ledger reports an empty bag without creating it. A 2.0
participant may therefore encounter an empty file left by an older sender.
Upgrade the participants before continuing.

MCP parent and worker code must also match. Internal worker protocol 2 uses
the private `--worker-v2` entry point, with no fallback. A new worker invoked
through the old `--worker` entry point returns
`worker_version_mismatch` / `not_submitted` before reading input or touching
a bag. An old worker rejects `--worker-v2` at argument parsing. Its raw exit
does not prove the failure stage to the new parent, which conservatively
returns `worker_failed` / `unknown` for a send with reconnect advice.
Reconnect after either an upgrade or downgrade. Do not retry automatically.
This deployment check is separate from the MCP wire protocol and provides
no authentication against another local process.

Rejoin under the same name if the native session restarted, or if a Codex
join used the older shared root ID. A join records a door, not a letter.
A Claude process whose inbox is unchanged needs no rejoin. Use CLI `join`
when you want to keep a current `bags --resume` hint. MCP joins deliberately
omit the conversation ID.

For new sessions, the host starts the configured MCP server automatically.
Ask the agent to join the intended bag under its own peer name.
For a new collaboration, ask each agent to join the same new bag under a
distinct name. Registered peers can use MCP
and CLI interchangeably at the same version.

## Tools

| Tool | Arguments | Effect |
|---|---|---|
| `postbag_join` | `name`, `bag="default"` | Register this caller's native door, creating a missing bag. A reused name takes over its previous holder. |
| `postbag_send` | `to`, `body`, `bag="default"`, `final=false` | Submit one letter and record it. `final=true` asks for no reply to this letter. |
| `postbag_read` | `bag="default"`, `limit=20`, `before=null` | Return recent records in chronological order. Pass `next_before` as `before` for older records. |
| `postbag_bags` | `limit=50`, `offset=0` | Inventory default and named bags. Pass `next_offset` as `offset` for another page. Its data carries `version`, the installed Postbag version that served the call. |

Page limits range from 1 to 100. `before` is an exclusive ledger record
number `n`, counting joins and historical opens as well as letters. These
record numbers never change. A letter's displayed number is its ordinal
among all recorded letters in the bag, not its position on the page.
Send bodies must contain 1 to 65,536 UTF-8 bytes and no NUL bytes.
Bag and peer names are a lowercase letter followed by up to 15 lowercase
letters, digits, or hyphens. `to` also accepts an initial `@`.

`final` is a strict Boolean. Omission means false. Integers, strings, null and
other types refuse before transport or ledger write. A true value replaces
the ordinary reply instructions with "Final letter. Do not reply to this
letter, even if its body asks for a reply." It closes nothing in the bag.
A later explicit send is ordinary unless it also sets `final=true`. The
flag and footer guide the recipient model. They cannot enforce silence or
prevent loops or prompt injection.

MCP selects bags only by name and ignores `POSTBAG_LEDGER`. Absolute paths
remain a CLI feature. A missing bag is created only by a valid join. A join
refused for its arguments or identity creates nothing. An I/O failure after
creation starts can leave a directory or partial file for inspection.
Send and read on a missing default or named bag create nothing, including
directories. Send points to `postbag_join`, and read points to `postbag_bags`.
Read and inventory calls create no files and probe no
sessions. Endpoint credentials and conversation IDs are excluded from their
results. Letter bodies are shared content, so read access still reveals the
correspondence. Inventory preserves readable rows when another bag is busy
or corrupt and reports `inventory_incomplete` with those rows. This is an
error result (`ok=false`, `isError=true`), with readable rows, pagination,
and errors retained in both structured content and JSON text.

Successful `data` fields are:

| Operation | Fields |
|---|---|
| Join | `bag`, `name`, `vendor`, `renamed`, `took` |
| Send | `bag`, `from`, `to`, `record`, `letter`, `final`, `submission_state` |
| Read | `bag`, `letters`, `peers`, `records`, `next_before` |
| Bags | `bags`, `total`, `offset`, `next_offset`, `errors`, `scope` |

Read's `letters` is the whole bag's recorded letter count. Each read record
has `n`, `at`, and `kind`. Join records add `peer` and `vendor`. Letter
records add `from`, `to`, `body`, `letter`, and Boolean `final`. Historical
open records retain `limit` as inert history. There are no derived exchange
fields. Postbag writes `final` in the raw ledger only when true. A hand-written
Boolean false is accepted as an ordinary letter. Reads and send receipts
return false when the field was absent.

Each inventory row has `bag`, `letters`, `last_letter`, and `peers`.
`letters` is an integer for a readable bag and null for an unavailable bag.
A bag with joins and no letters has count zero. Rows are separate snapshots,
not a consistent snapshot across all bags.

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
Ephemeral threads also cannot receive queued submissions. Use a persisted
session for a receiving peer. [Ephemeral target restriction](https://github.com/openai/codex/blob/rust-v0.157.1/codex-rs/app-server/src/request_processors/thread_queue_processor.rs#L255-L263).
Claude subagents sharing the same inbox act as the same peer. Postbag
does not create or supervise either kind of agent. A registered peer is not
evidence that its session is still running.

## Results and uncertain submissions

Application outcomes contain `ok`, `error_code`, `submission_state`, `message`,
and `data`, both as structured content and JSON text. Refusals set MCP
`isError`. Input schema failures use the SDK's standard MCP error result.
When a refusal has a recovery action, `data.recovery` identifies the action,
bag, and actor. Caller actions name `postbag_join`, `postbag_read`, or
`postbag_bags` in the message. A restarted recipient must rejoin from its own
session. Recovery guidance identifies who can resolve the problem and preserves the core's
stop-and-ask-human rule. It never performs an action or retries a send
automatically.

| `submission_state` | Meaning |
|---|---|
| `not_submitted` | This attempt did not submit a letter. Correct the reported problem before continuing. |
| `submitted` | The native transport returned successfully. Check `ok` to learn whether ledger recording also succeeded. This does not prove acceptance, reading, or execution. |
| `unknown` | Submission may have happened. Check the bag and recipient before considering another send. |
| `null` | The result is not a letter submission outcome. |

Successful sends include the sender, recipient, record and letter numbers,
and final flag. A ledger recording failure after successful
transport reports `recording_failed` and `submitted`. A native timeout,
partial socket write, nonzero queue exit, or worker crash can report
`unknown`. An empty ledger tail cannot establish that a letter was not sent.
Recording happens after native submission. If the process dies or recording
fails in between, a submitted letter can remain unrecorded and a later send
can reuse its letter number. Check the recipient before deciding whether
another send is appropriate. Postbag never retries
automatically. A failed flush or fsync can also leave a visible record whose
durability is uncertain.

Each call runs the installed module by absolute path in a fresh subprocess,
with private stdin and captured stdout and stderr. Worker imports ignore
the host project's directory and Python environment overrides. Output uses
ASCII JSON framing independent of the host locale. CLI globals and environment
cannot cross requests. The parent validates the worker's outer result fields,
JSON encoding, nesting, and submission state before exposing them to the host.
Successful sends must report `submitted`. Responses that fail these checks
become `worker_failed` with state `unknown` for sends. Operation-specific data
has no separate schema. MCP mutations use a nonblocking exclusive ledger lock.
A busy ledger reports `ledger_busy`
before native submission, so it cannot wait silently and send later.
An unexpected send failure whose position is uncertain reports
`operation_failed` with state `unknown`, including an unexpected
`BlockingIOError` outside the ledger-lock refusal.

Removing letter budgets does not remove resource limits. MCP's body and page
caps, worker-result depth checks and nonblocking ledger locks remain, as do
the native transport timeouts shared with the CLI. The CLI does not apply
MCP's 65,536-byte body cap. These controls do not bound the number of sends
or guarantee that every operation finishes within a deadline.

New ledger files use mode `0600`. Mutations preserve existing file modes and
refuse a file with group or other access or without owner read and write.
Making the ledger unwritable prevents new write opens. Mutations also check
the mode after taking the lock, so an existing waiter may refuse. An operation
past that check may finish, and read access can remain. Closing a Codex client
does not revoke a persisted thread's queue. Neither action recalls a submitted letter.

Cancelling a request does not cancel its worker while the server remains
alive. Graceful server shutdown waits for workers to finish and record.
There is no worker deadline that kills a send. A stalled filesystem operation
can therefore keep a worker and graceful shutdown waiting indefinitely.
A client can still forcibly terminate the server and its children. A timeout,
disconnect, forced shutdown, or lost response must therefore be treated as
an unknown outcome. Never retry automatically.

## Verification

The `test_mcp*.py` files use the real SDK and stdio subprocesses with isolated
homes, fake native executables, and private Unix sockets. The installed
`8b87b4f` wheel passed **157 MCP tests** outside the source checkout. The
extracted source archive passed **55 tests in `test_core_2.py`**. Both used
pytest 9.1.1 and treated `ResourceWarning` as an error. The wire suite covers
identity, isolation, secret redaction, malformed inputs and worker responses,
native failures, cancellation, join-created bags, missing-bag refusals,
strict `final`, concurrent sends and record cursors across legacy opens.
Current and legacy MCP wire clients are separate from the private
parent/worker protocol. A separate full-suite run passed **586 tests** with
private HOME and `ResourceWarning` as an error. All **13 CI jobs** passed
for the same commit. [Candidate CI](https://github.com/parasxos/postbag/actions/runs/36842969085).

Run the suite with:

```sh
.venv/bin/python -m pip install '.[dev,mcp]'
.venv/bin/python -m pytest -q
```

The `mcp` extra is required for the wire tests. A base-only development
installation skips them. CI tests the core without that extra, runs the MCP
suite separately, and runs the wire tests against an installed wheel outside
the source checkout.

The installed `8b87b4f` candidate passed the native gate on its first run with
Codex 0.158.0-alpha.2.1 and Claude Code 2.1.286 on macOS 27.0.1. Seven
model-authored tool calls made two joins and five sends. The check observed
an initial round trip, then no Claude send and no ledger change for
30.0668 seconds after receipt and turn completion of a final letter whose
body asked for a reply. A deliberately initiated ordinary letter and reply
then arrived in both directions. All three processes exited 0, with
no forced shutdown and closed endpoints.

The queue used default discovery in private state, not the personal desktop
daemon. Claude's local receipt markers were instrumentation rather than
Postbag replies. The final observation does not isolate the footer from the
rest of the model context or establish that every conversation will stop.
Exact provenance, permissions and receipt evidence are in
[native compatibility checks](native-compatibility.md).

Historical native runtime evidence and remaining limits are recorded in
[native-compatibility.md](native-compatibility.md). The installed 1.3.0
candidate passed a cross-vendor native round trip and spent-budget refusal
using default shared-server discovery in an isolated state directory, with
the current desktop executable and no queue wrapper or `--remote`. Earlier
checks covered explicit-remote routing and mixed CLI/MCP replies. These
checks did not modify or test the user's personal running daemon. Linux
fixture tests do not establish native vendor acceptance on Linux. A live
Claude `/clear` transition remains untested. Windows is unsupported.
