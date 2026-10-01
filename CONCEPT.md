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

## Five verbs

| Verb | Who | Effect |
|---|---|---|
| `join <vendor> [name]` | a peer, from inside its own session | records its door under a name, by default the vendor. Creates the bag if it does not exist. |
| `send @name` | a peer, from inside its own session | knocks on that door, then records the letter. `--final` marks the letter as one that asks for no reply. |
| `read` | anyone | prints the ledger, preceded by one line: the names held now and the number of letters |
| `bags` | anyone | inventories existing ledgers in scope: letters recorded, last recorded letter time, and registered names with vendors |
| `leave` | a peer, from inside its own session | withdraws its door's registration from the bag. Until a door joins again, letters to that name refuse and this door can neither send nor be sent to there. |

Every verb takes an optional `--bag NAME` before it. `join` creates any
bag that does not exist, default, named or path alike. `send` and `read`
on a missing bag create nothing, not even a directory, and refuse: `send`
points the caller to `join`, `read` points to `bags`. A `join` refused
for its arguments or its identity creates nothing. Once creation has
begun, an I/O failure or a crash can leave a directory or an empty or
partial file behind, and postbag never deletes or truncates on failure,
since another process may already hold the file open. A ledger that
already exists is never re-moded: if it grants group or other access, or
lacks owner read and write, every mutation refuses before parsing,
knocking or appending. `join` is the creating verb because it is
the first write in practice: a `send` needs a name that the sender's door
holds in that bag, and a bag with no join holds none. A mistyped `--bag`
on `join` therefore leaves a bag with one join and no letters. `bags`
lists it, no verb removes it, and it is a file you delete.

A bare command selects `POSTBAG_LEDGER`, a path, and otherwise `default`,
however many bags exist. `--bag` overrides both. In `POSTBAG_LEDGER`, `~`
is expanded and a relative path is made absolute for display and for
generated commands, and `--bag` takes the path as the shell hands it. A path
equal to the default ledger displays as `default`.

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
   same ending says to reply only when a reply advances the task, to send
   no courtesy acknowledgement and no unsolicited delivery check, and not
   to add a question or offer that needs no answer. A receipt that a human
   asked for is task, not courtesy. A final letter ends instead with one
   line that says not to reply to it even if its body asks for a reply,
   and it carries no reply command. The flag is the sender's statement
   and the footer is guidance to a model, not enforcement: the next send
   in the bag, from anyone, is legal and ordinary. Neither agent needs
   prior instruction.
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
   what remains when the letter is read. A letter record carries `final`
   only when it is true. Every record keeps its line number `n`, including
   joins and historical opens. `read N` shows the last N records, and MCP
   paging cursors are record numbers. A letter's displayed number is its
   position among the bag's letters.
5. **postbag has no brake.** It sets no limit on how many letters a bag
   holds or how fast they arrive, and it has no verb a human runs from a
   terminal to stop two sessions. A host that confirms each tool call
   gives its human a chance to intervene at every letter. That is an
   opportunity, not a bound. A host that confirms nothing leaves every
   letter to its model, and the footer is then the last word postbag has.
   The footer and the final flag are guidance, not a security boundary.
   The controls that exist belong to the hosts and the filesystem, and
   each has limits. Ending a Claude session closes its inbox, so sends to
   it refuse. Ending a Codex client does not: its saved thread can still
   accept queued letters, which it reads when resumed. Neither recalls a
   letter already queued or cancels a send in flight. Taking write
   permission from the bag makes later `send` and `join` refuse at their
   open, while `read` and `bags` still work on a readable file. A process
   that already holds the ledger finishes, and one already waiting for the
   lock rechecks the mode when it gets it. postbag sets the file mode only
   when it creates the file. A
   recipient's inbound policy, where its host offers one, can hold or
   refuse letters before its model sees them. Refusals tell the agent to
   stop and ask the human. That suffix is an instruction to the agent,
   not a claim that the human holds a verb. Who may run `join` and
   `send` is decided by the session variables the vendors themselves
   export.
6. **Everything the agents share is the repository.** The bridge moves
   text, never files. Work products travel through git.

## Leaving

`leave` is a recorded withdrawal, the one thing a session can do to stop
corresponding in a bag without ending itself. It appends a `leave` record
that carries the door's name, vendor and door fields, like a `join`
without its navigation metadata. Replaying it removes the binding, and
only when that name is still held by that exact door. A `leave` whose
name is held by another door, or by nobody, makes the ledger inconsistent
and the bag refuses to read, so a stale leave can never unregister a door
that took the name later. After a leave, a `send` to that name refuses as
not registered and says when it was left, and the door that left cannot
send in that bag until it joins again. `read` and `bags` still work.
Other bags and the session itself are untouched. A door that holds no name
in the bag cannot leave it, and is told to read the bag, never to join in
order to leave. A `leave` on a missing bag creates nothing.

The withdrawal is the door's, not the session's. A shared Claude inbox is
one door, so a subagent that leaves withdraws its parent and siblings
from that bag too. Letters already queued to a Codex thread still arrive,
and a `send` that took the ledger lock first finishes before the leave is
recorded. Once it is recorded, later lookups refuse until a `join`
restores a binding. A `join` after a leave is deliberate: a refusal that
follows a leave names the leave, so an old queued letter cannot talk a
departed door back in by accident. `leave` never deletes the bag or its
history. Over MCP it is `postbag_leave` with the bag alone, and the name
is derived from the door, never passed.

A `leave` record is a new kind. Readers older than 2.1 refuse a ledger
that holds one as not a record, and that is deliberate: a reader that
skipped a record it did not understand could keep a withdrawn binding and
deliver a letter wrongly. A bag written by 2.0 reads unchanged in 2.1.
Once a bag holds a leave, every reader of that bag must be 2.1 or later,
and a downgrade for that bag is unsupported. Deleting leave rows is not a
repair.

## Names

A name is a lowercase ASCII letter followed by up to fifteen lowercase
letters, digits or hyphens, so it pastes unquoted. `claude` and `codex` are
reserved for doors of that vendor, and a same-vendor pair needs distinct
names, since both defaults would take the same one. A door has one name and
a name has one door. The last `join` wins both ways, and `join` says what it
renamed or took. A name is an address, not authentication. A send to a name
nobody holds refuses and points to `read`, describing the latest
transition of that name: that it was left at a time, or that its last door
now holds another name. A door whose name was taken
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

Reply only when a reply advances the task. Do not send courtesy acknowledgements or unsolicited delivery checks, and do not add a question or offer that needs no answer.
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

Final letter. Do not reply to this letter, even if its body asks for a reply.
```

`final` is a strict boolean, absent meaning false, refused before any
transport or ledger write when it is anything else. A final letter closes
nothing in the bag. The next letter, from anyone, is ordinary. `read`
marks a final letter, and receipts and MCP reads return the flag. Nothing
infers it from history.

## Compatibility

A bag created by 2.0 has no `open` record. A bag reused from 1.x keeps
its `open` records as inert history. Mixed versions are not supported,
and nothing negotiates or rejects them: a 2.0 side always sends, a 1.x
side sends only inside the latest budget retained in that bag and counts
2.0 letters against it, past zero, while reading the `final` field and
hiding it. An `open` written by a 1.x tool into a 2.0 bag is honoured by
1.x and ignored by 2.0. A 2.0 tool reads every 1.x bag. Its `open` records
print as rows of history that change nothing, and its letters are numbered
by their position among the bag's letters, so a letter that 1.x showed as
the fourth of its second exchange may show as the sixteenth. Record line
numbers never change. `open` is no longer a verb, and `postbag open` is an
unknown verb like any other. The recovery hint for a missing bag on `send`
names `join`, since `join` creates it. The MCP server and its worker
carry a protocol version, and both skews refuse before any transport or
ledger write. A running 1.x server that launches a 2.0 worker file gets
a structured refusal, not submitted, that says to reconnect the server. A
2.0 server that launches a 1.x worker file sees only a raw exit it cannot
tell from a crash, so a send reports an unknown outcome and the other
tools report a failed worker, each with the same reconnect guidance.

## What is deliberately absent

Roles, topics, threads, acknowledgements, retries, a delivery server, a
Postbag configuration file, a protocol document for the agents, broadcast,
rooms, presence, peer discovery, a bag index, a current bag, bag liveness,
and, since 2.0, a letter budget, a rate limit and a human-only verb. Each
was considered and found to add a noun without adding a capability, or to
duplicate a control the hosts already have. Resource limits are not
budgets and stay: the native timeouts and the nonblocking ledger lock in
both interfaces, and over MCP the letter body cap, the page size and the
result depth cap. The CLI takes a body of any size its door accepts. The
bag holds any number of doors and a letter has one recipient. Two
sessions are the supported use.
More is experimental and promised nothing.
