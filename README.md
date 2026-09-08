# postbag

**Two agents, one bag of letters.** Any two Claude Code or Codex sessions
on the same machine, of the same vendor or not, write to each other. Each
letter reaches the other agent through its vendor's own wake-up door, lands
in one ledger, and counts against a human-set letter budget.

[![ci](https://github.com/parasxos/postbag/actions/workflows/ci.yml/badge.svg)](https://github.com/parasxos/postbag/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/postbag)](https://pypi.org/project/postbag/)

![postbag demo: two Claude Code sessions join as ada and bob, you open an exchange of four letters, ada asks bob for a review, bob answers, read shows the ledger](https://raw.githubusercontent.com/parasxos/postbag/v1.1.0/docs/assets/demo.gif)

*Real commands, real output, fake doors. The recording uses a temporary
ledger and two throwaway sockets, so no session or token is shown. Tape:
[docs/demo.tape](https://github.com/parasxos/postbag/blob/v1.1.0/docs/demo.tape).*

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

postbag needs Claude Code's per-session messaging socket and the `queue`
command [Codex added in 0.149](https://github.com/openai/codex/releases/tag/rust-v0.149.0).
Release 1.0.2 was verified end to end on macOS with Claude Code 2.1.263 and
Codex 0.153.4 from the ChatGPT desktop app. Linux passes CI but the live
exchange is not verified there. Windows is not supported. A Claude session
must export `CLAUDE_CODE_MESSAGING_SOCKET` and `CLAUDE_CODE_MESSAGING_TOKEN`
to the commands it runs, a Codex session must export `CODEX_SESSION_ID`, and
`codex queue --help` must work. Set `POSTBAG_CODEX` if the binary is not in
the ChatGPT app or on `PATH`.

## Quick start

Open two sessions on the same machine, one of each vendor or two of the same.

1. Ask each session to join: `postbag join claude` and `postbag join codex`.
   The name defaults to the vendor. Two sessions of the same vendor need
   distinct names, `postbag join claude ada` and `postbag join claude bob`,
   since both defaults would take the same one.
2. In a terminal of your own, outside both sessions:

   ```sh
   postbag open --limit 6
   ```

   Without `--limit` an exchange holds 12 letters.

3. Ask one session to send the first letter:

   ```sh
   postbag send @codex "Review my last commit. Reply with the top three findings."
   ```

   The recipient wakes with the letter. It begins "Letter 1 of 6 from
   @claude to @codex via postbag (exchange 1)", says how many letters are
   left, and ends with the one command that answers it, `postbag send
   @claude -` with the reply on stdin, so neither agent needs instructions.
   The last letter of the budget says "do not send a reply", and the next
   `send` refuses and tells the agent to stop and ask you. Names print with
   `@` and `send` accepts them with or without it.

4. Read the bag from anywhere with `postbag read`. Its first line lists the
   names the bag holds now and the open exchange, then the records follow.

After a session restarts, ask it to `join` again under the name it held. A
reply command names a name, not a door, so it reaches whoever holds that
name when it runs. If another door took the name, the sender's next `send`
refuses.

## Upgrading from 1.0

Ledgers written by 1.0 read without rewriting. A 1.0 `join` carries no
name, so legacy vendor peers read as `@claude` and `@codex`. Do not mix a
1.0 session with a 1.1 session: a 1.1 letter's reply command is
`postbag send @name -`, and a 1.0 `send` takes only `claude` or `codex`
without the `@`, so the 1.0 side cannot answer. Upgrade both sessions, then
ask each to `join` again.

## How it works

`join` writes the session's door into the ledger under a name: Claude
Code's per-session messaging socket and token, or Codex's thread id. `send`
knocks on the recipient's door, the socket or `codex queue`, then appends
the letter under a file lock, so two letters sent at once get distinct
numbers and one budget. Each `open` starts the next exchange, and letters
are numbered within it. The budget is shared by everyone in the bag. Two
sessions are the supported use. Three or more is experimental, `read` says
so, and every letter then lists the registered names. The ledger,
`~/.postbag/ledger.jsonl`, is the only state, and the default is shared
across projects. Set the same `POSTBAG_LEDGER` in both sessions and your
terminal for a separate bag. No daemon, no polling, no hooks, no server, no
config file. [CONCEPT.md](https://github.com/parasxos/postbag/blob/v1.1.0/CONCEPT.md)
is the whole specification in a page, with the table that maps Claude
Code's own words, `SendMessage` and a session's name, onto postbag's.

## Security and limits

- The ledger holds every Claude session token and every letter. Writes keep
  the file `0600` and new state directories are `0700`. An existing custom
  directory is left alone. `read` hides the door fields, `cat` does not.
  Keep the raw file out of git, logs and screenshots.
- A letter becomes a user turn in the recipient session. Trust both sessions
  with the task. postbag itself sends nothing off the machine, the vendor
  sessions forward the letter to their model services like any prompt.
- A name is an address, not authentication. `open` refuses inside a
  session. Both checks read the vendors' session variables: a guardrail
  against mixed-up roles, not protection against another process running
  as you.
- Unattended delivery to Claude was verified with bypass permissions. Other
  modes may hold the letter for your approval. Codex needs permission to
  write the ledger and connect to the Claude socket.
- "Delivered" means submitted through the door, not read. A timeout or a
  crash between submission and recording can leave a letter in doubt. There
  are no acknowledgements and no retries. Check the recipient before sending
  again.

postbag is a small bridge for two existing sessions. Tools that do more, and
what they do, are listed in [docs/readme-research.md](https://github.com/parasxos/postbag/blob/v1.1.0/docs/readme-research.md).

[Concept](https://github.com/parasxos/postbag/blob/v1.1.0/CONCEPT.md) · [Security](https://github.com/parasxos/postbag/security/policy) · [Changelog](https://github.com/parasxos/postbag/blob/v1.1.0/CHANGELOG.md) ·
[Contributing](https://github.com/parasxos/postbag/blob/v1.1.0/.github/CONTRIBUTING.md) · [MIT](https://github.com/parasxos/postbag/blob/v1.1.0/LICENSE)
