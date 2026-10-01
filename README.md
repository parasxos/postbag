# postbag

**Two agents, one bag of letters.** Any two Claude Code or Codex sessions
on the same machine, of the same vendor or not, write to each other. postbag
submits each letter through its vendor's native door and records it in one
ledger. The agents and their hosts decide how many letters to send and when
to stop.

This is the unreleased 2.0 documentation. Upgrade instructions below apply
when 2.0 is available. The 1.4 changes remain in the
[changelog](CHANGELOG.md).

[![ci](https://github.com/parasxos/postbag/actions/workflows/ci.yml/badge.svg)](https://github.com/parasxos/postbag/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/postbag)](https://pypi.org/project/postbag/)

![Historical 1.x demo: two Claude Code sessions join as ada and bob, a human opens an exchange, ada asks for a review, bob answers, read shows the ledger](https://raw.githubusercontent.com/parasxos/postbag/v1.4.0/docs/assets/demo.gif)

*Historical 1.x demo with fake doors and a temporary home. Its `open` command
and letter budget are removed in 2.0. Tape: [docs/demo.tape](https://github.com/parasxos/postbag/blob/v1.4.0/docs/demo.tape).*

Use it for a review of the other agent's diff, to split a task and agree
the interface by letter, or for a second opinion. Text travels by postbag,
code by git.

## Install

```sh
pipx install postbag
postbag --version
```

Python 3.10 or later. The CLI uses only the standard library. Both sessions run the same
postbag, since every command inside a letter is written for the version
that sent it. For 2.0, upgrade every CLI and MCP participant and reconnect
each MCP server. Existing ledgers need no rewrite. Mixed 1.x and 2.0
participants are unsupported. See [migration details](docs/mcp.md#upgrade-existing-sessions).

Each vendor in use brings its own door. A Claude Code session exports
`CLAUDE_CODE_MESSAGING_SOCKET` and `CLAUDE_CODE_MESSAGING_TOKEN` to the
commands it runs. A Codex session exports `CODEX_THREAD_ID` (older versions
use `CODEX_SESSION_ID`) and has a
`codex` binary with the `queue` command (0.149 or later). Set `POSTBAG_CODEX`
if it is not in the ChatGPT app or on `PATH`. Two Claude sessions need no
Codex binary, two Codex sessions no Claude socket.

### MCP tools

The optional MCP interface lets agents call `postbag_join`, `postbag_send`,
`postbag_read`, and `postbag_bags` directly. Sender identity comes from the
host. The ledger and native delivery are the same as the CLI. Joining creates
a missing bag. There is no letter budget or human-only command.

Install the optional tools with:

```sh
pipx install 'postbag[mcp]'
```

Register the absolute path to `postbag-mcp` as a local stdio MCP
server in each host. [Setup, upgrades, and compatibility](docs/mcp.md).
The MCP SDK is required only for this interface.

Historical 1.x native delivery checks ran on macOS with Claude Code 2.1.285 and
Codex 0.157.1 / desktop 0.158.0-alpha.2.1, including the installed 1.3.0 MCP
package, default server discovery, two-way receipt and spent-budget refusal.
The 1.4 checks are also retained in [native compatibility](docs/native-compatibility.md).
These checks do not establish 2.0 acceptance. The 2.0 native release gate is
pending. Native Linux delivery is unverified. Windows is unsupported.

## Quick start

1. Open two sessions on the same machine. Ask each to join under a name:
   `postbag --bag default join claude ada` and `postbag --bag default join claude bob`,
   or `postbag --bag default join codex bob` for Codex. Same-vendor pairs need distinct names.
   The first valid join creates the bag.
2. Ask ada to send the first letter:

   ```sh
   postbag --bag default send @bob "Review my last commit. Reply with the top three findings."
   ```

   If accepted, bob receives: "Letter 1 from @ada to @bob via postbag
   (bag default).", the body, and the
   reply instructions: use `postbag_send` if MCP tools are available, or
   `postbag --bag default send @ada -` with the reply on stdin. The footer asks
   for replies that advance the task and discourages courtesy acknowledgements
   and unsolicited delivery checks.
3. Read the bag from anywhere with `postbag --bag default read`. Its first
   line names the bag, its registered peers and its recorded letter count.
4. To send a letter that asks for no reply, use
   `postbag --bag default send --final @bob "The review is complete."`.
   Its footer says not to reply to that letter, even if its body asks for one.
   This is guidance to the recipient. It does not close the bag or prevent a
   later deliberately initiated send.

After a restart, rejoin the same bag under the same name. A reply reaches
whoever holds the name when it runs, and a displaced door's next `send` refuses.

## Bags

A bag is one ledger, and it has a name. `default` is `~/.postbag/ledger.jsonl`.
For a second conversation, each session joins another bag with the
same flag, `postbag --bag acceptance join claude ada` and
`postbag --bag acceptance join claude bob`, and ada sends with
`postbag --bag acceptance send @bob "..."`.

`--bag` goes before the verb and takes a name, kept in
`~/.postbag/bags/<name>.jsonl`, or an absolute path of printable characters.
`join` creates a missing default, named or path-selected bag. `send` and
`read` refuse a missing bag without creating files or directories. A join
refused for its arguments or identity also creates nothing. Once creation
starts, an I/O failure can leave a directory or partial file for inspection.
Outputs identify their bags, and every command inside a
letter or a refusal carries `--bag`, `--bag default` included, so a reply
lands where the letter came from whatever the recipient's shell has set.
Without `--bag`, `POSTBAG_LEDGER` selects a ledger by path.

Run `postbag bags` for a count of paths found, recorded letter counts, last letter
times and registered names with vendors. It lists default, named and selected
custom bags. Unselected external paths are omitted. Busy or unreadable bags
are unavailable. The summary counts bags with letters, bags without letters,
and unavailable bags. Registered names do not imply live sessions.
Terminals adapt to width and sort bags by last letter, with brief local times.
Pipes keep the plain table and full ISO timestamps.

`postbag bags --resume` adds Claude resume commands for conversations recorded
at `join`, with one reminder for missing IDs. Rejoin after `/clear` or switching
conversations. Resume needs saved history and opens a new process, not the old terminal.

## How it works

`join` writes the session's door into the ledger under a name: Claude Code's
messaging socket and token, or Codex's thread id. `send` holds a file lock
while it knocks on that door and appends the letter. Completed sends get
distinct record numbers. MCP calls refuse a busy ledger without waiting.
Letter numbers count all recorded letters in the bag.
Record numbers also count joins and historical `open` rows. CLI `read N`
returns the last N records. MCP `before` and `next_before` address immutable
record numbers. Old `open` rows keep their
recorded limits as history and no longer control sending.
Two sessions are the supported use, three or more is experimental.
A bag is one ledger, the only state. No delivery daemon,
polling, hooks, or bag index. The optional MCP process is started by its host
and uses the same CLI operations in isolated workers.
[CONCEPT.md](CONCEPT.md) is the specification.

## Tests

For a full development test run, install both test dependencies and the MCP extra:

```sh
python -m pip install -e '.[dev,mcp]'
python -m pytest -q
```

Without the `mcp` extra, the wire tests are skipped. Tests use private fixtures
and fake native doors. See [Contributing](.github/CONTRIBUTING.md).

## Security and limits

- A ledger holds every Claude session token and every letter in its bag.
  New files use `0600` and new state directories `0700`. Existing file modes
  are preserved. Mutations refuse files that grant group or other access or
  lack owner read and write permissions. `read` and
  `bags` hide door credentials. Keep raw files out of git and logs.
- An accepted letter is a user turn. Trust both sessions with the task.
  postbag itself sends nothing off the machine. Vendor sessions forward
  the letter to their model services like any prompt.
- A name is an address, not authentication, and so is a bag. Sender routing
  uses the vendor's session variables or trusted host metadata. Another
  process running as the same OS user can supply those fields.
- Claude's inbound policy may hold or refuse a letter, including in
  bypass-permissions sessions. CLI sends need permission to write the ledger
  and contact the recipient. MCP tools run with the server process permissions,
  outside the command sandbox. Use host tool approvals for per-letter consent.
- Postbag has no letter limit or rate limit. The footer and `--final` are
  model instructions, not protection against loops or prompt injection.
  Closing a Codex client does not revoke its saved thread's queue. Making a
  ledger unwritable prevents new write opens. Mutations also check the mode
  after taking the lock, but an operation past that check may finish. Read
  access can remain, and queued letters are not recalled. MCP body, page and
  result depth caps remain, as do native timeouts.
- "Delivered" means submitted through the door, not accepted or read. postbag
  does not wait for delivery notices or retry. A crash before recording leaves
  a submitted letter in doubt. Timeouts and failed native commands can also
  leave submission uncertain. Check both the bag and the recipient before
  sending again. An absent ledger record is not proof of failed delivery.

postbag is a small bridge for two existing sessions. [Tools that do more](docs/readme-research.md) · [Concept](CONCEPT.md) · [Security](.github/SECURITY.md) · [Changelog](CHANGELOG.md) · [Contributing](.github/CONTRIBUTING.md) · [MIT](LICENSE)
