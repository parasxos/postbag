# postbag: two sessions correspond by letters

## The idea

Two agents on one machine talk the way two people in adjacent offices do.
One writes a letter and slides it under the other's door. The door is
the vendor's native input to that agent. Every letter goes into one bag.
Nothing else exists. Any two sessions can correspond, of the same vendor
or not. postbag carries letters and keeps the record. How many letters
the agents write, and when they stop, is decided by the agents and the
hosts that run them, not by postbag.

## Four nouns

| Noun | Definition |
|---|---|
| **peer** | A door with a name, given at `join`. |
| **door** | The native way to reach a peer. Claude: its inbox socket and token. Codex: its thread id, reached with `codex queue`. A door is its vendor and those fields. A change to the fields makes a new door. |
| **letter** | Text from one peer to another. Numbered in its bag, timestamped, delivered, then recorded. A sender may mark a letter final. |
| **ledger** | One append-only file, the bag. The whole history, the only state. A bag has a name, like a door: `default` is `~/.postbag/ledger.jsonl`, any other name is `~/.postbag/bags/<name>.jsonl`, and an absolute path is a bag too. |

## Four verbs

| Verb | Who | Effect |
|---|---|---|
| `join <vendor> [name]` | a peer, from inside its own session | records its door under a name, by default the vendor. Creates the bag if it does not exist. |
| `send @name` | a peer, from inside its own session | knocks on that door, then records the letter. `--final` marks the letter as closing the thread. |
| `read` | anyone | prints the ledger, preceded by one line: the names held now and the number of letters |
| `bags` | anyone | inventories existing ledgers in scope: letters recorded, last recorded letter time, and registered names with vendors |

Every verb takes an optional `--bag NAME` before it. `join` creates any
bag that does not exist. `send` and `read` refuse one. `join` is the
creating verb because it is always the first write: a `send` needs a name
that the sender's door holds in that bag, and a bag with no join holds none.
A mistyped `--bag` on `join` therefore leaves a bag with one join and no
letters. `bags` lists it, no verb removes it, and it is a file you delete.

A bare command selects `POSTBAG_LEDGER`, a path, and otherwise `default`,
however many bags exist. `--bag` overrides both. In `POSTBAG_LEDGER`, `~`
is expanded and a relative path is made absolute for display and for
generated commands, and `--bag` takes the path as the shell hands it. A path
equal to the default ledger displays as `default`. `read` and `bags` create
nothing.

## Inventory

`bags` scans the default ledger and direct `<name>.jsonl` files under
`~/.postbag/bags`, using the bag-name grammar and excluding `default.jsonl`.
It also includes an existing custom path selected by `--bag` or
`POSTBAG_LEDGER`. A selected custom alias of an already listed regular file
is not repeated. The default or named label is retained. A missing selected
path is omitted. The scan is not recursive, and unselected paths outside
these locations cannot be discovered.

The count covers discovered candidate paths, including unavailable ledgers.
Each readable row shows how many letters the bag holds, the last recorded
letter's time or that no letter is recorded, and the names and vendors held
now. It prints neither letter bodies nor door credentials. Registration does
not establish whether a session is live. The status summary counts bags
with letters, bags without letters, and unavailable bags, and omits zero
counts.

Each row is a separate snapshot under a nonblocking shared ledger lock,
not one consistent snapshot across bags. Busy, unreadable or invalid ledgers
are marked unavailable. Other rows still print and the command exits 1.
A directory scan failure is reported, not presented as an exhaustive empty
inventory. Output states the scan's scope. No file is created or changed,
no door is contacted, and there is no index or current-bag pointer.

In a terminal, bags with recent recorded letters come first. A table at
100 columns or wider becomes separate bag blocks in narrower terminals.
Paths and peer groups wrap without dropping text. Times use the local
timezone: `Today HH:MM`, `Yesterday HH:MM`, or `YYYY-MM-DD HH:MM`. Future
timestamps use the absolute date and are marked as future. Styling is
disabled when `NO_COLOR` is present, even empty, or `TERM=dumb`. Piped
output keeps the original table, ordering and full ISO timestamps, without
styling.

Claude `join` also records `CLAUDE_CODE_SESSION_ID` when it is a valid UUID.
This optional `session_id` is navigation metadata, never part of the door.
`bags --resume` keeps the inventory layout and adds a copyable command below
each bag for conversations with valid IDs at the latest join. Missing IDs get
one rejoin reminder after the inventory, not one hint per peer. It reads no
vendor registry or transcripts and does not establish whether history is
saved. Rejoin after `/clear` or switching conversations. Resume opens saved
history in a new process, not the current terminal. Ordinary `bags` and
`read` do not display this metadata.

## Principles

The optional local MCP interface exposes `join`, `send`, `read`, and `bags`
as tools. The host starts its stdio process. Each tool uses an isolated
worker and the same ledger and native transport as the CLI. Identity comes
from host metadata or inherited inbox fields, never model arguments.
The default bag and named bags are exposed, without filesystem path arguments.
Joining creates a bag from either interface. See
[MCP setup and outcomes](docs/mcp.md).

1. **The sender is the door, not a flag.** `send` runs inside a session,
   and that session joined as one door. The letter is from that door.
   There is no `--from`. The shell's door fields must match exactly one
   name in the bag. None or several refuse. A shell inside two vendors'
   sessions says which door it registers at `join`.
2. **The door is native.** No daemon, no polling, no hooks. Delivery
   uses the mechanism each vendor built to reach its own agent. The
   recipient's permissions still apply.
3. **The letter teaches its reader how to answer.** Each delivered
   letter begins with its number in the bag, which is the bag's running
   tally of letters, its sender and its recipient. Then comes the body.
   A letter ends with the way to reply: in a named or default bag, the
   Postbag MCP send tool for a reader that has it, and in every bag the
   one shell command that replies. Both name the bag and the sender. The
   same ending says to reply only when the letter needs an answer, that
   delivery is already recorded so confirming receipt is never an answer,
   and not to end a reply with a question or offer that needs no answer.
   A final letter ends instead with one line that says the thread is
   closed and not to reply even if the body asks for one, and it carries
   no reply command. Neither agent needs prior instruction.
4. **The ledger is the truth.** The ledger records completed sends: a
   letter is in it if and only if it was delivered and then recorded.
   Delivered means submitted through the door, the socket write returned
   or `codex queue` exited 0. postbag does not read delivery notices or
   wait for an acknowledgement. Submission does not prove the recipient
   accepted, read or acted on the letter. Submission and recording are
   separate steps. A crash between them leaves a submitted letter
   unrecorded. The next letter may carry the same number. Doors and names
   are read from the ledger, never from anywhere else. Names are read by
   replaying the joins in order: each join drops the earlier holder of
   that name and the earlier name of that door, and what remains is the
   bag. History is a file you can `cat`. Ledgers written before names, and
   ledgers written when bags still had budgets, read without rewriting.
   The roster in an envelope is a snapshot at submission, not a promise of
   what remains when the letter is read.
5. **postbag has no brake.** It sets no limit on how many letters a bag
   holds or how fast they arrive, and it has no verb a human runs from a
   terminal to stop two sessions. A host that confirms tool calls bounds
   the conversation. A host that does not, does not, and a letter arriving
   in a session that confirms nothing is acted on by that session's model
   alone. The controls that exist are the hosts' own: end a session, and
   its door stops answering. Make the bag unwritable, and both `send` and
   `join` refuse. Set the recipient's inbound policy to hold or refuse
   letters where the host offers one. What postbag adds is the envelope,
   which tells every reader when not to answer, and refusals that tell the
   agent to stop and ask the human. That suffix is an instruction to the
   agent, not a claim that the human holds a verb. Who may run `join` and
   `send` is decided by the session variables the vendors themselves export.
6. **Everything the agents share is the repository.** The bridge moves
   text, never files. Work products travel through git.

## Names

A name is a lowercase ASCII letter followed by up to fifteen lowercase
letters, digits or hyphens, so it pastes unquoted. `claude` and `codex` are
reserved for doors of that vendor, and a same-vendor pair needs distinct
names, since both defaults would take the same one. A door has one name and
a name has one door. The last `join` wins both ways, and `join` says what it
renamed or took. A name is an address, not authentication. A send to a name
nobody holds refuses and points to `read`. If the last door to hold that
name still holds another, the refusal says so. A door whose name was taken
learns it at its next `send`, which refuses. A reply command names a name,
not a door: it reaches whoever holds the name when it runs. Names print
with `@`, and `send` accepts them with or without it. A bag name follows
the same grammar, and `default` is reserved. A bag path must contain only
printable characters.

## The same words as Claude Code

| Claude Code | postbag |
|---|---|
| `SendMessage` to a session | `send @name` |
| a session's name | a peer's name |
| a message | a letter |
| `ListAgents` | no equivalent. `read` and `bags` show registered names, not live agents |

## Envelope, verbatim

```
Letter 4 from @ada to @bob via postbag (bag acceptance).

<body>

Reply only if this letter needs an answer. Delivery is already recorded, so do not reply only to acknowledge or confirm receipt, and do not end a reply with a question or offer you do not need answered.
If you have Postbag MCP tools, call postbag_send with bag acceptance and to @ada.
Otherwise reply with:
postbag --bag acceptance send @ada - <<'POSTBAG'
<your reply>
POSTBAG
Change POSTBAG at both ends to a word that does not occur in your reply.
```

When the bag holds names other than the sender and the recipient, the
first line is followed by the complete list: "Registered names in this bag:
@ada, @bob, @cleo." Registered, not present.

A final letter, sent with `--final` or `final: true`:

```
Letter 5 from @ada to @bob via postbag (bag acceptance).

<body>

This letter closes the thread. Do not reply, even if the body asks for one.
```

A final letter closes nothing in the bag. The next letter, from anyone,
is ordinary. It is the sender's way to end without inviting an answer.

## Compatibility

A 2.0 bag has no `open` record and a 1.x `send` in it refuses with "no
exchange is open". Mixed versions are not supported: a 2.0 side always
sends, a 1.x side sends only inside a 1.x budget, and an `open` written by
a 1.x tool into a 2.0 bag is honoured by 1.x and ignored by 2.0. A 2.0 tool
reads every 1.x bag. Its `open` records print as rows of history that change
nothing, and its letters are numbered by their position among the bag's
letters, so a letter that 1.x showed as the fourth of its second exchange
may show as the sixteenth. `open` is no longer a verb, and `postbag open`
is an unknown verb like any other. The recovery hint for a missing bag
names `join`, since `join` creates it.

## What is deliberately absent

Roles, topics, threads, acknowledgements, retries, a delivery server, a
Postbag configuration file, a protocol document for the agents, broadcast,
rooms, presence, peer discovery, a bag index, a current bag, bag liveness,
and, since 2.0, a letter budget, a rate limit and a human-only verb. Each
was considered and found to add a noun without adding a capability, or to
duplicate a control the hosts already have. The bag holds any number of
doors and a letter has one recipient. Two sessions are the supported use.
More is experimental and promised nothing.
