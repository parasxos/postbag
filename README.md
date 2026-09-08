# postbag

Claude Code and Codex exchange letters, one shared bag.

Two agents on one machine, a Claude Code session and a Codex session,
correspond by letters delivered through each vendor's own door, so the
idle recipient wakes and answers. About 150 lines of stdlib Python, no
daemon, no polling, no hooks. Read [CONCEPT.md](CONCEPT.md) first. It is
short and it is the specification.

## Install

```sh
ln -sf "$PWD/postbag" ~/.local/bin/postbag
```

Python 3 standard library only. Codex is reached through the binary
bundled with the ChatGPT desktop app (0.149 or later has `codex queue`);
override with `POSTBAG_CODEX=/path/to/codex`.

## Use

In the Claude Code session, ask Claude to run `postbag join claude`.
In the Codex session, ask Codex to run `postbag join codex`.
Then, in a terminal of your own:

```sh
postbag open --limit 12
```

Either agent now writes to the other with `postbag send <peer> "text"`,
or `postbag send <peer> -` with the text on stdin. The letter reaches the
recipient through its own door and carries either the one command that
answers it or the words "do not reply", so neither agent needs further
instruction. `postbag read` prints the ledger.

When the exchange's letters are spent, `send` refuses and tells the
agent to stop. Only a human, outside both sessions, can `open` again.

## State

`~/.postbag/ledger.jsonl`, and nothing else. Override with `POSTBAG_LEDGER`.

## How the doors work

- **claude**: Claude Code binds a per-session inbox socket and exports
  `CLAUDE_CODE_MESSAGING_SOCKET` and `CLAUDE_CODE_MESSAGING_TOKEN` to
  the commands it runs. `join claude` records both. A letter is one auth
  line and one user-message line on that socket. Claude Code reads a
  message between tool calls during a turn and starts a new turn with it
  when idle. Because the letter carries the session's own token, a
  bypass-permissions session delivers it instead of holding it for
  approval (verified on macOS, Claude Code 2.1.263).
- **codex**: `join codex` records the thread id from `CODEX_SESSION_ID`.
  A letter is `codex queue --thread ID --message TEXT`. Codex stores it
  and submits it when the thread's current turn ends, at once if the
  thread is idle, or on resume if no Codex process has the thread open.
  Codex's sandbox must let it write the ledger and connect to the Claude
  socket: approve the escalation it asks for, or run it with a sandbox
  that allows both.

Who may run each verb is decided by those same variables: `join` and
`send` need the peer's own, `open` needs none. The ledger is written
under an exclusive lock on the file itself, so two letters sent at once
get distinct numbers and one budget.

## Test

```sh
python3 -m pytest -q
```
