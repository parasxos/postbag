<div align="center">

# 📮 postbag

### Two agents, one bag of letters.

**Claude Code and Codex, on one machine, correspond by letter.** Each letter
is delivered through the vendor's own wake-up mechanism, so the idle agent
wakes and answers. Every letter lands in one append-only ledger. A human
opens each exchange with a budget of letters. When it is spent, sending
refuses and tells the agent to stop.

```
pipx install git+https://github.com/parasxos/postbag@v1.0.0
```

One Python file, about 250 lines, standard library only. No daemon, no
polling, no hooks, no server, no config file.

![ci](https://github.com/parasxos/postbag/actions/workflows/ci.yml/badge.svg)
![python](https://img.shields.io/badge/Python-3.10%E2%80%933.14-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![platform](https://img.shields.io/badge/platform-macOS%20%2B%20Linux-orange)
![stdlib](https://img.shields.io/badge/stdlib-only-blueviolet)
![deps](https://img.shields.io/badge/dependencies-zero-brightgreen)

</div>

---

## ✨ What you can do

🔍 **Cross-review.** Claude writes the parser, Codex reads it cold and sends
back what it would change. Then swap. Each agent sees the other's work as a
letter in its own session, with the one command that answers it.

✂️ **Split a task.** One agent takes the backend, the other the tests. They
agree on the interface by letter, then work in the same repository. Text
travels by postbag, code travels by git.

🧠 **Second opinion.** Stuck on a design choice? Ask the other agent in one
letter and get an answer without leaving your session or pasting context by
hand.

🪞 **Mirrored implementation.** Both agents implement the same change from
the same brief. Compare the two, keep the better one, and let them argue
about the diff.

🤝 **Handoff.** Finish your part, write one letter that says what is done and
what is next, and the other agent picks it up on its next turn. The ledger is
the handoff document.

**In use today.** The author ran a 50-letter exchange in which Claude and
Codex co-authored a slide deck with cross-review. This release was built by
the two agents collaborating over postbag: mirrored plans, mirrored
implementations, cross-review of every merge.

## ⚡ Why it's different

Two agents on one machine can already talk. Every other way adds a moving
part that has to be running, watched, or fed by hand.

| Approach | Wakes the idle agent? | State lives in | Moving parts | Who bounds the conversation |
|---|---|---|---|---|
| Shared file plus polling | Only while a poll loop runs | A file, plus each agent's loop | A loop in every session | Whoever remembers to stop the loop |
| Message broker | Yes, if a consumer is attached | The broker | A daemon, a client library, a config | The broker's config |
| MCP server | Only when the agent calls a tool | The server process | A server per session, plus registration | Nobody by default |
| Human copy-paste | Yes, the human is the transport | The human's clipboard | The human's attention | The human, at every turn |
| **postbag** | **Yes, through the vendor's own door** | **One JSONL file** | **One script** | **The human, once, with a letter budget** |

Delivery uses the mechanism each vendor built to reach its own agent.
Claude Code has a per-session messaging socket. Codex has `codex queue`.
postbag knocks on the right one and records the letter. Nothing runs in the
background.

## 🛡️ Built to be trusted

- 🧾 **The ledger is the truth.** A letter exists if and only if it was
  delivered and then recorded. Doors and budgets are read from the ledger and
  nowhere else. History is one file you can `cat`.
- 🛑 **The budget is the brake.** A delivered letter becomes a user turn in
  the recipient session. Two agents will keep answering each other. The
  exchange holds exactly the letters its opener granted. When they are spent,
  `send` refuses and tells the agent to stop and ask the human.
- 🙋 **Only a human can open.** `open` refuses to run inside either agent's
  session. Neither agent can extend its own budget.
- 🚪 **Every refusal says stop.** Each error an agent can meet ends with
  "stop and ask the human", so a failed send never turns into a retry loop.
- 🔒 **Private by construction.** The ledger is created with mode 0600 in a
  0700 directory, opened without following symlinks, validated on every
  read, and written under an exclusive lock. Two letters sent at once get
  distinct numbers and share one budget.
- 🧱 **Nothing to run, nothing to configure.** No daemon, no polling, no
  hooks, no server, no config file. Two environment variables are the only
  knobs, and both have working defaults.
- 📜 **A short spec.** [CONCEPT.md](CONCEPT.md) is the specification: five
  nouns, four verbs, six principles. The code follows it line by line.

## 🚀 Quick start

1. **Install** (Python 3.10 or later, macOS or Linux):

   ```bash
   pipx install git+https://github.com/parasxos/postbag@v1.0.0
   postbag --version
   ```

   Or clone and symlink the checked-in `postbag` executable into your
   `PATH`. It runs from the checkout with nothing installed.

2. **Each agent joins from inside its own session.** Ask Claude Code to run
   the first, and Codex to run the second:

   ```bash
   postbag join claude
   postbag join codex
   ```

3. **You open an exchange** from a terminal of your own, outside both
   sessions:

   ```bash
   postbag open --limit 6
   ```

4. **Either agent writes.** Ask Claude to send the first letter:

   ```bash
   postbag send codex "Review src/parser.py for unhandled input. Reply with the top three findings."
   ```

   Codex wakes with the letter, answers with the command the letter carries,
   and Claude wakes in turn. When the budget is spent, the last letter says
   "do not reply" and the next `send` refuses.

5. **Read the bag** at any time, from anywhere:

   ```bash
   postbag read
   ```

   ```
      1  2026-09-08T10:02:11+02:00  join   claude
      2  2026-09-08T10:02:40+02:00  join   codex
      3  2026-09-08T10:03:05+02:00  open   6 letters
      4  2026-09-08T10:03:30+02:00  letter claude -> codex
         Review src/parser.py for unhandled input. Reply with the top three findings.
      5  2026-09-08T10:05:12+02:00  letter codex -> claude
         1. parse_line accepts an empty string and returns None without logging.
         2. The date branch swallows ValueError and falls through to the default.
         3. No upper bound on field count, a long line allocates unbounded memory.
      6  2026-09-08T10:07:48+02:00  letter claude -> codex
         Fixed all three in 4f2a9c1. Please re-review the date branch only.
   ```

What the recipient actually sees is the letter wrapped in a short envelope:

```
Letter 4 from claude via postbag. If it needs an answer, reply with:
postbag send claude - <<'POSTBAG'
...
POSTBAG
Choose a delimiter that does not occur in your reply. Otherwise do nothing.

Review src/parser.py for unhandled input. Reply with the top three findings.
```

The envelope is the whole protocol. Neither agent needs prior instruction.

> 💡 The Codex binary ships inside the ChatGPT desktop app on macOS and is
> found automatically. Elsewhere, `codex` must be on `PATH`, or set
> `POSTBAG_CODEX=/path/to/codex`. `codex queue` needs Codex 0.149 or later.

## 🔁 A workflow for paired work

Give both agents the same goal, then ask them to repeat this at each stage.
It is how this release was made.

| Stage | Each agent, independently | Agree by letter before moving on |
|---|---|---|
| Plan | Inspect the problem and propose a small solution. | Scope, acceptance checks, who owns which files. |
| Implement | Build a candidate on its own branch or worktree. | Compare diffs and combine the strongest parts. |
| Test | Run the checks and read the other candidate. | Fix failures, test the combined result. |
| Ship | Review the release diff and notes. | One agent performs the release, the other verifies it. |

Letters carry disagreements, commit ids and evidence. Work products move
through git. Never let both agents edit the same file at once.

## 🚪 How the doors work

A door is the native way to reach a peer. `join` records it in the ledger.
`send` knocks on it, then records the letter.

**claude.** Claude Code binds a per-session inbox socket and exports
`CLAUDE_CODE_MESSAGING_SOCKET` and `CLAUDE_CODE_MESSAGING_TOKEN` to the
commands it runs. `join claude` records both. A letter is one auth line and
one user-message line written to that socket. Claude Code reads the message
between tool calls during a turn, or starts a new turn with it when idle.
Because the letter carries the session's own token, a session running with
bypass permissions delivers it instead of holding it for approval. Verified
on macOS with Claude Code 2.1.263.

**codex.** `join codex` records the thread id from `CODEX_SESSION_ID`. A
letter is `codex queue --thread ID --message TEXT`. Codex stores it and
submits it when the thread's current turn ends, at once if the thread is
idle, or on resume if no Codex process has the thread open. Verified on
macOS with Codex 0.153.

**Who may run what.** The same session variables decide it. `join` and
`send` need the peer's own variables, so `send codex` can only come from a
Claude session and `send claude` only from a Codex session. `open` needs
none, and refuses if either set is present.

**State.** `~/.postbag/ledger.jsonl`, and nothing else. Override with
`POSTBAG_LEDGER`, using the same value in both sessions and your terminal.
Two different ledgers are two independent pairs with two budgets.

## 🔐 Security

Plain facts, so you can decide whether this fits your machine. The longer
version is [SECURITY.md](SECURITY.md).

- **The Claude session token is stored in the ledger.** `join claude` writes
  the socket path and the token as a record. The file is mode 0600 in a
  0700 directory. Anyone who can read it can write a user turn into that
  Claude session. Treat the ledger like a credential file, because it is one.
  `postbag read` never prints it. `cat` does.
- **A letter is a user turn.** The recipient treats the body as if you had
  typed it. This is the feature, and it is also the risk. The other agent can
  ask yours to do anything you could ask it. The human's letter budget is the
  brake, and it is the only brake.
- **Bypass permissions is required on the Claude side.** Without it, Claude
  Code holds the incoming message for approval and the letter waits for you.
  Run Claude Code in bypass-permissions mode only in a repository and on a
  machine where you accept what that means.
- **The Codex sandbox must be opened a little.** Codex has to write the
  ledger and connect to the Claude socket. Approve the escalation it asks
  for, or run it with a sandbox profile that allows both.
- **Delivered is not read.** `send` reports success when the door accepted
  the letter: the socket took the bytes, or `codex queue` exited 0. That is
  not proof the agent read it or acted on it. A crash between the knock and
  the append can leave a delivered letter unrecorded. There is no
  acknowledgement, retry or exactly-once guarantee. When in doubt, read the
  ledger and the recipient session before sending again.
- **Nothing leaves the machine.** postbag talks to a local Unix socket and a
  local `codex` process. There is no network code in it.
- **Session variables are a guardrail, not a wall.** They stop the human,
  Claude and Codex from mixing up their verbs. They do not authenticate
  against another program running as the same user.

## 🔧 Troubleshooting

Every error postbag prints ends with "stop and ask the human". These are the
ones you will meet.

| Symptom | Fix |
|---|---|
| `join claude from inside a claude session` | Run `join` from inside that agent's session, not your terminal. The session variables are how postbag knows who is asking. |
| `open is the human's verb` | Your shell carries a session variable. Run `open` from a terminal you opened yourself, or `unset` `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN` and `CODEX_SESSION_ID` first. |
| `send codex is claude's verb; run it inside a claude session` | Addressing one peer names the other. Only Claude sends to Codex, and only Codex sends to Claude. |
| `codex has not joined` or `claude has not joined` | Ask that agent to run `postbag join <peer>` from its own session. |
| `codex's door did not answer` | The session restarted and its door is stale. Re-run `postbag join codex` in the new session, then send again. Same for `claude`. |
| `no codex at ...; set POSTBAG_CODEX` | Point `POSTBAG_CODEX` at the binary. On macOS it is inside the ChatGPT app. Elsewhere put `codex` on `PATH`. |
| `codex queue` is not a recognised command | Update Codex. `codex queue` arrived in 0.149. |
| `the exchange's letters are spent` | Working as designed. Open a new exchange from your own terminal with `postbag open --limit N`. |
| `no exchange is open` | Same fix. Only a human can open one. |
| Send succeeds but Claude Code shows a pending approval instead of answering | Claude Code is not in bypass-permissions mode. Restart it with bypass permissions and re-run `postbag join claude`. |
| Codex send fails with a sandbox or permission error | Approve the escalation Codex asks for, or run Codex with a sandbox that allows writing `~/.postbag` and connecting to the Claude socket. |
| `ledger line N is not a record` | The ledger was edited or truncated. Fix that line or move the file aside and start fresh. Both agents must `join` again. |
| `cannot open the ledger` or `not a regular file` | The path is a symlink, a pipe, or its directory is not writable. Check `POSTBAG_LEDGER` and permissions. |
| `letter N was submitted to codex's door but not recorded` | The append failed after delivery. Check the recipient session and the ledger before sending again. |

## ❓ FAQ

**Can I use two Claude Code sessions, or two Codex sessions?**
No. There are exactly two peers, `claude` and `codex`, and addressing one
names the other. That is what removes `--from`, roles, and a protocol
document. A different pair would be a different tool.

**How do I know the other agent read my letter?**
You do not, from `send` alone. It reports that the door accepted the
letter. Look at `postbag read` for the reply, or at the recipient session.

**Does postbag move files?**
No. It moves text. Work products travel through git, which both agents
already share. The letter says which commit to look at.

**What happens when a session restarts?**
Its door goes stale. The next `send` to it fails and tells you to re-run
`join` in the new session. The ledger keeps every earlier record.

**Can an agent give itself more letters?**
No. `open` refuses to run inside either session. When the budget is spent
the agent is told to stop and ask the human. That is the design, not a
limitation.

**Why not just paste between the two windows?**
You can, and postbag does the same thing without you as the transport. The
idle agent wakes on its own, the letter carries the reply command, and the
whole exchange is in one file afterwards.

**Windows?**
No. postbag uses Unix sockets and file locks from the standard library.
macOS is where it is verified. Linux works when `codex` is on `PATH`.

## 🧪 Develop

```sh
git clone https://github.com/parasxos/postbag.git && cd postbag
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q
```

Tests use a temporary ledger and fake doors. They never reach a real
session. See [CONTRIBUTING.md](CONTRIBUTING.md) and
[CHANGELOG.md](CHANGELOG.md).

---

<div align="center">

One file · four verbs · one ledger · MIT

Built for one Mac, and for any machine where Claude Code and Codex sit side by side.

</div>
