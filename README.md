# postbag

**Two agents, one bag of letters.** Any two Claude Code or Codex sessions
on the same machine, of the same vendor or not, write to each other. Each
letter reaches the other agent through its vendor's own wake-up door, lands
in one ledger, and counts against a human-set letter budget.

[![ci](https://github.com/parasxos/postbag/actions/workflows/ci.yml/badge.svg)](https://github.com/parasxos/postbag/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/postbag)](https://pypi.org/project/postbag/)

![postbag demo: two Claude Code sessions join as ada and bob, you open an exchange of four letters, ada asks bob for a review, bob answers, read shows the ledger](https://raw.githubusercontent.com/parasxos/postbag/v1.1.0/docs/assets/demo.gif)

*Real commands, real output, fake doors: a temporary ledger and two throwaway
sockets, so no session or token is shown. Tape: [docs/demo.tape](https://github.com/parasxos/postbag/blob/v1.1.0/docs/demo.tape).*

Use it to have one agent review the other's diff, to split a task between
them and agree the interface by letter, or to get a second opinion without
pasting context by hand. Text travels by postbag, code travels by git.

## Install

Python 3.10 or later, standard library only.

```sh
pipx install postbag
postbag --version
```

Or from the tag: `pipx install git+https://github.com/parasxos/postbag@v1.1.0`.

Each vendor in use brings its own door. A Claude Code session needs its
per-session messaging socket and must export `CLAUDE_CODE_MESSAGING_SOCKET`
and `CLAUDE_CODE_MESSAGING_TOKEN` to the commands it runs. A Codex session
needs the `queue` command [Codex added in 0.149](https://github.com/openai/codex/releases/tag/rust-v0.149.0),
must export `CODEX_SESSION_ID`, and `codex queue --help` must work. Set
`POSTBAG_CODEX` if the binary is not in the ChatGPT app or on `PATH`. Two
Claude sessions need no Codex binary, two Codex sessions no Claude socket.
Verified live on macOS: 1.0.2 end to end with Claude Code 2.1.263 and
Codex 0.153.4 from the ChatGPT desktop app, and 1.1.0 between two Claude
Code 2.1.263 sessions registered as @ada and @bob, one two-letter exchange
with a challenge and a quoted reply through each session's own socket, then
the spent-budget refusal. Linux passes CI but the live exchange is not
verified there. Windows is not supported.

## Quick start

Open two sessions on the same machine. Either role can be any supported
vendor: a Claude and a Codex session, or two of the same.

1. Ask each session to join under a name: `postbag join claude ada` and
   `postbag join claude bob`, or `postbag join codex bob` for a Codex
   session. The name defaults to the vendor, so a same-vendor pair needs
   distinct names. Names print with `@` and `send` takes them either way.
2. In a terminal of your own, outside both sessions, run
   `postbag open --limit 6`. Without `--limit` an exchange holds 12 letters.
3. Ask ada to send the first letter:

   ```sh
   postbag send @bob "Review my last commit. Reply with the top three findings."
   ```

   bob wakes with the letter: "Letter 1 of 6 from @ada to @bob via postbag
   (exchange 1)", how many letters are left, the body, and the one command
   that answers, `postbag send @ada -` with the reply on stdin. Neither agent
   needs instructions. The last letter says "do not send a reply", and the
   next `send` refuses and tells the agent to stop and ask you.

4. Read the bag from anywhere with `postbag read`. Its first line lists the
   names the bag holds now and the open exchange, then the records follow.

After a restart, a session must `join` again under the name it held. A reply
command names a name, not a door: it reaches whoever holds the name when it
runs, and if another door took the name, the sender's next `send` refuses.

## Upgrading from 1.0

Ledgers written by 1.0 read without rewriting, and legacy vendor peers read
as `@claude` and `@codex`. Do not mix a 1.0 session with a 1.1 session: a
1.0 `send` takes only `claude` or `codex` without the `@`, so it cannot run
the reply command in a 1.1 letter. Upgrade both, then ask each to `join` again.

## How it works

`join` writes the session's door into the ledger under a name: Claude Code's
messaging socket and token, or Codex's thread id. `send` knocks on that door,
the socket or `codex queue`, then appends the letter under a file lock, so
two letters sent at once get distinct numbers and one budget. Each `open`
starts the next exchange, letters are numbered within it, and the budget is
shared by everyone in the bag. Two sessions are the supported use. Three or
more is experimental, `read` says so, and every letter then lists the
registered names. The ledger, `~/.postbag/ledger.jsonl`, is the only state
and is shared across projects by default. Set the same `POSTBAG_LEDGER` in
both sessions and your terminal for a separate bag. No daemon, no polling,
no hooks, no server, no config file. [CONCEPT.md](https://github.com/parasxos/postbag/blob/v1.1.0/CONCEPT.md)
is the whole specification in a page, with the envelope's exact shape and
the table that maps Claude Code's own words onto postbag's.

## Security and limits

- The ledger holds every Claude session token and every letter. Writes keep
  the file `0600` and new state directories are `0700`. An existing custom
  directory is left alone. `read` hides the door fields, `cat` does not.
  Keep the raw file out of git, logs and screenshots.
- A letter becomes a user turn in the recipient session. Trust both sessions
  with the task. postbag itself sends nothing off the machine, the vendor
  sessions forward the letter to their model services like any prompt.
- A name is an address, not authentication. `open` refuses inside a session.
  Both checks read the vendors' session variables: a guardrail against
  mixed-up roles, not protection against another process running as you.
- Unattended delivery to Claude was observed with bypass permissions on the
  tested versions. Other modes may hold the letter for your approval. Codex
  needs permission to write the ledger and connect to the Claude socket.
- "Delivered" means submitted through the door, not read. A timeout or a
  crash between submission and recording leaves a letter in doubt, and there
  are no acknowledgements or retries. Check the recipient before sending again.

postbag is a small bridge for two existing sessions. Tools that do more, and
what they do, are listed in [docs/readme-research.md](https://github.com/parasxos/postbag/blob/v1.1.0/docs/readme-research.md).

[Concept](https://github.com/parasxos/postbag/blob/v1.1.0/CONCEPT.md) · [Security](https://github.com/parasxos/postbag/security/policy) · [Changelog](https://github.com/parasxos/postbag/blob/v1.1.0/CHANGELOG.md) · [Contributing](https://github.com/parasxos/postbag/blob/v1.1.0/.github/CONTRIBUTING.md) · [MIT](https://github.com/parasxos/postbag/blob/v1.1.0/LICENSE)
