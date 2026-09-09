# postbag

**Two agents, one bag of letters.** Any two Claude Code or Codex sessions
on the same machine, of the same vendor or not, write to each other. Each
letter reaches the other agent through its vendor's own wake-up door, lands
in one ledger, and counts against a human-set letter budget.

[![ci](https://github.com/parasxos/postbag/actions/workflows/ci.yml/badge.svg)](https://github.com/parasxos/postbag/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/postbag)](https://pypi.org/project/postbag/)

![postbag demo: two Claude Code sessions join as ada and bob, you open an exchange of four letters, ada asks bob for a review, bob answers, read shows the ledger](https://raw.githubusercontent.com/parasxos/postbag/v1.2.0/docs/assets/demo.gif)

*Real commands, real output, fake doors: a temporary home and two throwaway
sockets, so no session or token is shown. Tape: [docs/demo.tape](https://github.com/parasxos/postbag/blob/v1.2.0/docs/demo.tape).*

Use it for a review of the other agent's diff, to split a task and agree
the interface by letter, or for a second opinion. Text travels by postbag,
code by git.

## Install

```sh
pipx install postbag
postbag --version
```

Python 3.10 or later, standard library only. From the tag instead:
`pipx install git+https://github.com/parasxos/postbag@v1.2.0`.

Each vendor in use brings its own door. A Claude Code session needs its
per-session messaging socket and must export `CLAUDE_CODE_MESSAGING_SOCKET`
and `CLAUDE_CODE_MESSAGING_TOKEN` to the commands it runs. A Codex session
needs the `queue` command [Codex added in 0.149](https://github.com/openai/codex/releases/tag/rust-v0.149.0),
must export `CODEX_SESSION_ID`, and `codex queue --help` must work. Set
`POSTBAG_CODEX` if the binary is not in the ChatGPT app or on `PATH`. Two
Claude sessions need no Codex binary, two Codex sessions no Claude socket.
Verified live on macOS: 1.0.2 across Claude Code 2.1.263 and Codex 0.153.4
from the ChatGPT app, 1.1.0 between two Claude Code 2.1.263 sessions with a
two-way exchange and the spent-budget refusal, 1.2.0 with a Claude Code and a
Codex session in a named bag, a two-letter exchange and the spent-budget
refusal. Linux passes CI, live delivery is unverified there. Windows is unsupported.

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

   bob wakes with the letter: "Letter 1 of 6 from @ada to @bob via postbag
   (exchange 1, bag default)", how many letters are left, the body, and the
   one command that answers, `postbag --bag default send @ada -` with the
   reply on stdin. Neither agent needs instructions. The last letter says
   "do not send a reply", and the next `send` refuses and says stop.
4. Read the bag from anywhere with `postbag --bag default read`. Its first
   line names the bag, its names and the open exchange, then the records.

After a restart, rejoin the same bag under the same name. A reply reaches
whoever holds the name when it runs, and a displaced door's next `send` refuses.

## Named bags

For a second conversation, open a second bag first, in your own terminal:
`postbag --bag acceptance open --limit 6`. Each session then joins with the
same flag, `postbag --bag acceptance join claude ada` and `... join claude
bob`, and ada sends with `postbag --bag acceptance send @bob "..."`. `--bag`
goes before the verb and takes a name, kept in `~/.postbag/bags/<name>.jsonl`,
or an absolute path of printable characters, and `default` is
`~/.postbag/ledger.jsonl`. Only `open` creates a named bag, the other verbs
refuse one that does not exist. The default bag and a custom path are created
on first write, and `read` never creates a file. Each command's output
identifies the bag, and every command inside a letter or a refusal carries
`--bag`, `--bag default` included, so a reply lands where the letter came from
whatever the recipient's shell has set. `ls ~/.postbag/bags` lists them.
Without `--bag`, `POSTBAG_LEDGER` still selects a ledger by path.

## Upgrading

Ledgers written by 1.0 and 1.1 read without rewriting, and legacy vendor
peers read as `@claude` and `@codex`. A 1.1 `send` refuses `--bag`, and every
1.2 reply command carries it, so scoped commands need 1.2 at both ends, the
default bag included. Upgrade both, then ask each to `join` again. An older
CLI reaches a bag by path: `POSTBAG_LEDGER='/abs/path' postbag send ...`.

## How it works

`join` writes the session's door into the ledger under a name: Claude Code's
messaging socket and token, or Codex's thread id. `send` knocks on that door,
then appends the letter under a file lock, so two letters sent at once get
distinct numbers and one budget. Each `open` starts the next exchange, and its
budget is shared by everyone in the bag. Two sessions are the supported use,
three or more is experimental. A bag is one ledger, the only state. No daemon,
no polling, no hooks, no server, no config file, no bag index.
[CONCEPT.md](https://github.com/parasxos/postbag/blob/v1.2.0/CONCEPT.md) is the whole specification in a page.

## Security and limits

- A ledger holds every Claude session token and every letter in its bag.
  Writes keep the file `0600` and new state directories `0700`. `read` hides
  the door fields, `cat` does not. Keep raw files out of git and logs.
- A letter becomes a user turn in the recipient session, so trust both with
  the task. postbag itself sends nothing off the machine, the vendor sessions
  forward the letter to their model services like any prompt.
- A name is an address, not authentication, and so is a bag. `open` refuses
  inside a session. Both checks read the vendors' session variables: a
  guardrail against mixed-up roles, not protection against another process.
- Unattended delivery to Claude was observed with bypass permissions on the
  tested versions, other modes may hold the letter for your approval. Codex
  needs permission to write the ledger and connect to the Claude socket.
- "Delivered" means submitted through the door, not read. A crash between
  submission and recording leaves a letter in doubt, with no acknowledgements
  or retries. Check the recipient before sending again.

postbag is a small bridge for two existing sessions. [Tools that do more](https://github.com/parasxos/postbag/blob/v1.2.0/docs/readme-research.md) · [Concept](https://github.com/parasxos/postbag/blob/v1.2.0/CONCEPT.md) · [Security](https://github.com/parasxos/postbag/security/policy) · [Changelog](https://github.com/parasxos/postbag/blob/v1.2.0/CHANGELOG.md) · [Contributing](https://github.com/parasxos/postbag/blob/v1.2.0/.github/CONTRIBUTING.md) · [MIT](https://github.com/parasxos/postbag/blob/v1.2.0/LICENSE)
