# postbag

**Two agents, one bag of letters.** Any two Claude Code or Codex sessions
on the same machine, of the same vendor or not, write to each other. postbag
submits each letter through its vendor's native door, records it in one
ledger, and counts it against a letter budget that only you can set.

[![ci](https://github.com/parasxos/postbag/actions/workflows/ci.yml/badge.svg)](https://github.com/parasxos/postbag/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/postbag)](https://pypi.org/project/postbag/)

![postbag demo: two Claude Code sessions join as ada and bob, you open an exchange of four letters, ada asks bob for a review, bob answers, read shows the ledger](https://raw.githubusercontent.com/parasxos/postbag/v1.3.0/docs/assets/demo.gif)

*Real commands, real output, fake doors: a temporary home and two throwaway
sockets, so no session or token is shown. Tape: [docs/demo.tape](https://github.com/parasxos/postbag/blob/v1.3.0/docs/demo.tape).*

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
that sent it.

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
host. The ledger, native delivery, and shared budget are the same as the CLI.
Only the human can open or replenish an exchange.

Install the optional tools with:

```sh
pipx install 'postbag[mcp]'
```

Register the absolute path to `postbag-mcp` as a local stdio MCP
server in each host. [Setup, upgrades, and compatibility](https://github.com/parasxos/postbag/blob/v1.3.0/docs/mcp.md).
The MCP SDK is required only for this interface.

Native delivery has been checked on macOS with Claude Code 2.1.285 and
Codex 0.157.1 / desktop 0.158.0-alpha.2.1, including the installed 1.3.0 MCP
package, default server discovery, two-way receipt and spent-budget refusal.
Linux passes CI, but live delivery is unverified there. Windows is unsupported.

## Quick start

1. Open two sessions on the same machine. Ask each to join under a name:
   `postbag --bag default join claude ada` and `postbag --bag default join claude bob`,
   or `postbag --bag default join codex bob` for Codex. Same-vendor pairs need distinct names.
2. In a terminal of your own, outside both sessions, run
   `postbag --bag default open --limit 6`. An exchange holds 12 by default.
3. Ask ada to send the first letter:

   ```sh
   postbag --bag default send @bob "Review my last commit. Reply with the top three findings."
   ```

   If accepted, bob receives: "Letter 1 of 6 from @ada to @bob via postbag
   (exchange 1, bag default)", how many letters are left, the body, and the
   one command that answers, `postbag --bag default send @ada -` with the
   reply on stdin. Neither agent needs instructions. The last letter says
   "do not send a reply", and the next `send` refuses and says stop.
4. Read the bag from anywhere with `postbag --bag default read`. Its first
   line names the bag, its names and the open exchange, then the records.

After a restart, rejoin the same bag under the same name. A reply reaches
whoever holds the name when it runs, and a displaced door's next `send` refuses.

## Bags

A bag is one ledger, and it has a name. `default` is `~/.postbag/ledger.jsonl`.
For a second conversation, open a second bag first, in your own terminal:
`postbag --bag acceptance open --limit 6`. Each session then joins with the
same flag, `postbag --bag acceptance join claude ada` and
`postbag --bag acceptance join claude bob`, and ada sends with
`postbag --bag acceptance send @bob "..."`.

`--bag` goes before the verb and takes a name, kept in
`~/.postbag/bags/<name>.jsonl`, or an absolute path of printable characters.
Only `open` creates a named bag. `join`, `send` and `read` refuse a missing
one. Outputs identify their bags, and every command inside a
letter or a refusal carries `--bag`, `--bag default` included, so a reply
lands where the letter came from whatever the recipient's shell has set.
Without `--bag`, `POSTBAG_LEDGER` selects a ledger by path.

Run `postbag bags` for a count of paths found, remaining budgets, last letter
times and registered names with vendors. It lists default, named and selected
custom bags. Unselected external paths are omitted. Busy or unreadable bags
are unavailable. Budgets do not expire. Registered names do not imply live sessions.
Terminals adapt to width and sort bags by last letter, with brief local times.
Pipes keep the plain table and full ISO timestamps.

`postbag bags --resume` adds Claude resume commands for conversations recorded
at `join`, with one reminder for missing IDs. Rejoin after `/clear` or switching
conversations. Resume needs saved history and opens a new process, not the old terminal.

## How it works

`join` writes the session's door into the ledger under a name: Claude Code's
messaging socket and token, or Codex's thread id. `send` knocks on that door,
then appends the letter under a file lock, so two letters sent at once get
distinct numbers and one budget. Each `open` starts the next exchange, and its
budget is shared by everyone in the bag. Two sessions are the supported use,
three or more is experimental. A bag is one ledger, the only state. No delivery daemon,
polling, hooks, or bag index. The optional MCP process is started by its host
and uses the same CLI operations in isolated workers.
[CONCEPT.md](https://github.com/parasxos/postbag/blob/v1.3.0/CONCEPT.md) is the whole specification in a page.

## Security and limits

- A ledger holds every Claude session token and every letter in its bag.
  Writes keep the file `0600` and new state directories `0700`. `read` and
  `bags` hide door credentials. Keep raw files out of git and logs.
- An accepted letter is a user turn. Trust both sessions with the task.
  postbag itself sends nothing off the machine. Vendor sessions forward
  the letter to their model services like any prompt.
- A name is an address, not authentication, and so is a bag. `open` refuses
  inside a session. Both checks read the vendors' session variables: a
  guardrail against mixed-up roles, not protection against another process.
- Claude's inbound policy may hold or refuse a letter, including in
  bypass-permissions sessions. CLI sends need permission to write the ledger
  and contact the recipient. MCP tools run with the server process permissions,
  outside the command sandbox; use host tool approvals for per-letter consent.
- "Delivered" means submitted through the door, not accepted or read. postbag
  does not wait for delivery notices or retry. A crash before recording leaves
  a submitted letter in doubt. Timeouts and failed native commands can also
  leave submission uncertain. Check both the bag and the recipient before
  sending again; an absent ledger record is not proof of failed delivery.

postbag is a small bridge for two existing sessions. [Tools that do more](https://github.com/parasxos/postbag/blob/v1.3.0/docs/readme-research.md) · [Concept](https://github.com/parasxos/postbag/blob/v1.3.0/CONCEPT.md) · [Security](https://github.com/parasxos/postbag/security/policy) · [Changelog](https://github.com/parasxos/postbag/blob/v1.3.0/CHANGELOG.md) · [Contributing](https://github.com/parasxos/postbag/blob/v1.3.0/.github/CONTRIBUTING.md) · [MIT](https://github.com/parasxos/postbag/blob/v1.3.0/LICENSE)
