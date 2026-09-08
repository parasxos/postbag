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
Then, in any terminal:

```sh
bridge open "Review the parser rewrite"
```

Either agent now writes to the other with `bridge send <peer> "text"`
and the recipient wakes with the letter. Each letter carries the one
command that answers it, so neither agent needs further instruction.
`bridge read` prints the ledger.

An exchange holds at most `BRIDGE_LIMIT` letters (default 12). When the
budget is spent, `send` refuses until a human runs `bridge open` again.

## State

`~/.bridge/ledger.jsonl` is the history. `~/.bridge/<peer>.json` is a
door. Override the directory with `BRIDGE_HOME`.

## How the doors work

- **claude**: Claude Code binds a per-session inbox socket and exports
  `CLAUDE_CODE_MESSAGING_SOCKET` and `CLAUDE_CODE_MESSAGING_TOKEN` to
  the commands it runs. `join claude` records both. A letter is one auth
  line and one user-message line on that socket. The token makes the
  message count as the session's own child, so it is delivered even in a
  bypass-permissions session, and starts a turn if the session is idle.
- **codex**: `join codex` records the thread id, from `CODEX_SESSION_ID`
  or `--thread`. A letter is `codex queue --thread ID --message TEXT`,
  which is delivered when the current turn ends and wakes an idle thread.

## Test

```sh
python3 -m pytest -q
```
