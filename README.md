# bridge

Two agents on one machine, a Claude Code session and a Codex session,
correspond by letters. Read [CONCEPT.md](CONCEPT.md) first. It is short
and it is the specification.

## Install

```sh
ln -sf "$PWD/bridge" ~/.local/bin/bridge
```

Python 3 standard library only. Codex is reached through the binary
bundled with the ChatGPT desktop app (0.149 or later has `codex queue`);
override with `BRIDGE_CODEX=/path/to/codex`.

## Use

In the Claude Code session, ask Claude to run `bridge join claude`.
In the Codex session, ask Codex to run `bridge join codex`.
Then, in a terminal of your own:

```sh
bridge open --limit 12
```

Either agent now writes to the other with `bridge send <peer> "text"`,
or `bridge send <peer> -` with the text on stdin. The letter reaches the
recipient through its own door and carries the one command that answers
it, so neither agent needs further instruction. `bridge read` prints the
ledger.

When the exchange's letters are spent, `send` refuses and tells the
agent to stop. Only a human, outside both sessions, can `open` again.

## State

`~/.bridge/ledger.jsonl`, and nothing else. Override with `BRIDGE_LEDGER`.

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

The ledger is written under an exclusive lock on the file itself, so two
letters sent at once get distinct numbers and one budget.

## Test

```sh
python3 -m pytest -q
```
