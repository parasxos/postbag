# postbag: two sessions correspond by letters

## The idea

Two agents on one machine talk the way two people in adjacent offices do.
One writes a letter and slides it under the other's door. The door is
whatever wakes that agent natively. Every letter goes into one bag.
Nothing else exists. Any two sessions can correspond, of the same vendor
or not.

## Five nouns

| Noun | Definition |
|---|---|
| **peer** | A door with a name, given at `join`. |
| **door** | The native way to reach a peer. Claude: its inbox socket and token. Codex: its thread id, reached with `codex queue`. A door is its vendor and those fields; a change to the fields makes a new door. |
| **letter** | Text from one peer to another. Numbered within its exchange, timestamped, delivered, then recorded. |
| **exchange** | A budget of letters, opened by a human. Each `open` starts the next exchange and closes the one before it. |
| **ledger** | One append-only file, the bag. The whole history, the only state. A bag has a name, like a door: `default` is `~/.postbag/ledger.jsonl`, any other name is `~/.postbag/bags/<name>.jsonl`, and an absolute path is a bag too. |

## Four verbs

| Verb | Who | Effect |
|---|---|---|
| `join <vendor> [name]` | a peer, from inside its own session | records its door under a name, by default the vendor |
| `open` | a human, outside agent sessions | starts an exchange with a budget of letters. Every `send` spends the most recent exchange, and a new `open` replaces any unspent letters. |
| `send @name` | a peer, from inside its own session | knocks on that door, then records the letter |
| `read` | anyone | prints the ledger, preceded by one line: the names held now and the open exchange |

Every verb takes an optional `--bag NAME` before it. `open` creates a
named bag that does not exist, the other verbs refuse one.

A bare command selects `POSTBAG_LEDGER`, a path, and otherwise `default`,
however many bags exist. `--bag` overrides both. In either, `~` is
expanded, a relative `POSTBAG_LEDGER` is made absolute for display and
for generated commands, and a path equal to the default ledger displays
as `default`. The default bag and a path are still created on the first
write, and `read` creates nothing.

## Principles

1. **The sender is the door, not a flag.** `send` runs inside a session,
   and that session joined as one door. The letter is from that door.
   There is no `--from`. The shell's door fields must match exactly one
   name in the bag; none or several refuse. A shell inside two vendors'
   sessions says which door it registers at `join`.
2. **The door is native.** No daemon, no polling, no hooks. Delivery
   uses the mechanism each vendor built to reach its own agent.
3. **The letter teaches its reader how to answer.** Each delivered
   letter begins with its number in the exchange, its sender and its
   recipient, and the shared budget. Then comes the body. A non-final
   letter ends with the one command that replies, and that command names
   the bag. The final letter carries
   no command and says instead not to send a reply. Neither agent needs
   prior instruction.
4. **The ledger is the truth.** The ledger records completed sends: a
   letter is in it iff it was delivered and then recorded. Delivered means
   submitted through the door, the socket write returned or `codex queue`
   exited 0. Neither door acknowledges, and neither proves the agent read
   it. Submission and recording are two steps, not one; a crash between
   them leaves a submitted letter unrecorded, and the next letter may carry
   the same number. Doors, names and budgets are read from the ledger,
   never from anywhere else. Names are read by replaying the joins in
   order: each join drops the earlier holder of that name and the earlier
   name of that door, and what remains is the bag. History is a file you
   can `cat`. Ledgers written before names read without rewriting. `read N`
   numbers and groups records from the full ledger before showing the tail,
   so every displayed group carries its exchange label even when its open
   is not shown. The counts and any roster in an envelope are a snapshot at
   submission, not a promise of what remains when the letter is read.
5. **The human bounds the conversation.** An exchange holds the letters
   its opener granted. When they are spent, `send` refuses and tells the
   agent to stop. Every refusal an agent can meet tells it to stop and
   ask the human. Who may run each verb is decided by the session
   variables the vendors themselves export, the same signal for `join`,
   `open` and `send`.
6. **Everything the agents share is the repository.** The bridge moves
   text, never files. Work products travel through git.

## Names

A name is a lowercase ASCII letter followed by up to fifteen lowercase
letters, digits or hyphens, so it pastes unquoted. `claude` and `codex` are reserved for
doors of that vendor, and a same-vendor pair needs distinct names, since
both defaults would take the same one. A door has one name and a name has one door, the
last `join` wins both ways, and `join` says what it renamed or took. A
name is an address, not authentication. A send to a name nobody holds
refuses and points to `read`; if the last door to hold that name still
holds another, the refusal says so. A door whose name was
taken learns it at its next `send`, which refuses. A reply command names
a name, not a door: it reaches whoever holds the name when it runs. Names
print with `@`; `send` accepts them with or without it. A bag name follows
the same grammar, and `default` is reserved. A bag path must contain only
printable characters.

## The same words as Claude Code

| Claude Code | postbag |
|---|---|
| `SendMessage` to a session | `send @name` |
| a session's name | a peer's name |
| a message | a letter |
| `ListAgents` | no verb; the first line of `read` lists registered names, not live agents |

## Envelope, verbatim

With letters left:

```
Letter 4 of 12 from @ada to @bob via postbag (exchange 3, bag acceptance).
8 letters left in this exchange, shared by everyone in the bag.

<body>

If it needs an answer, reply with:
postbag --bag acceptance send @ada - <<'POSTBAG'
<your reply>
POSTBAG
Change POSTBAG at both ends to a word that does not occur in your reply.
Do not reply only to acknowledge.
```

When the bag holds names other than the sender and the recipient, the
second line ends with the complete list: "Registered names in this bag:
@ada, @bob, @cleo." Registered, not present.

Last letter:

```
Letter 12 of 12 from @ada to @bob via postbag (exchange 3, bag default).
The last letter of this exchange; do not send a reply, even if the body asks for one.

<body>
```

## What is deliberately absent

Roles, topics, threads, acknowledgements, retries, a server, a
configuration file, a protocol document for the agents, broadcast, rooms,
presence, discovery, a bag index, a current bag, bag liveness, bag
discovery. Each was considered and found to add a noun without
adding a capability. The bag holds any number of doors, a letter has one
recipient, and the budget is shared. Two sessions are the supported use;
more is experimental and promised nothing.
