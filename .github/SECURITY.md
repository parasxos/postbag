# Security

## What postbag trusts

postbag trusts the local OS account and the sessions that joined the bag.
CLI `join`, `send` and `leave` use environment variables the vendors export inside
their own sessions. MCP uses trusted host metadata or inherited inbox fields.
These fields select the caller's door. They are not authentication against
another program running as the same user. A name is an address, not
authentication. Version 2.0 has no human-only verb.

## What the ledger holds

Each selected bag, `~/.postbag/ledger.jsonl` by default, a named bag under
`~/.postbag/bags`, or a custom path from `--bag` or `POSTBAG_LEDGER`, holds
every letter body and every registered door: each Codex thread id, and each
Claude messaging socket path and session token. Several doors of one vendor
can be registered. New ledger files use `0600` and new state directories
`0700`. Existing file and directory modes are preserved. Every mutation
refuses an existing ledger that grants group or other access or lacks owner
read and write permissions, before parsing, contacting a door or appending.
Anyone who can read that file can submit messages to its registered Claude
inboxes. The recipient's policy still governs acceptance.

`postbag read` and `postbag bags` hide door credentials and print registered
names and vendors on purpose. Inventory also shows recorded letter counts and
last recorded letter timestamps, but no letter bodies. It reads ledgers
without contacting sessions. Registration does not establish liveness.

`bags --resume` explicitly shows Claude conversation IDs recorded at `join`,
with commands to reopen saved history. They are navigation metadata, not
credentials. It neither looks up sessions nor runs the displayed commands.
`cat` hides nothing. Keep the ledger out of git, issues, logs and screenshots.

## What a letter can do

A letter accepted by the recipient becomes a user turn. Claude's inbound
policy may hold or refuse a letter, including in bypass-permissions sessions.
The [recorded live checks](../docs/native-compatibility.md) observed
unattended delivery. That is an observation, not an exemption from the
recipient's permissions. postbag does not claim a sender permission mode or
change the recipient's policy. Use postbag only between sessions you would
trust with the same task.

Version 2.0 has no letter budget or rate limit. The ordinary footer asks for
replies that advance the task. A final letter asks for no reply to that letter,
even if its body asks for one. Both are instructions to a model. They are not
a security boundary against prompt injection or a guarantee against loops.
A final letter does not disable later sends.

MCP calls run with the server's permissions, outside the agent's command
sandbox. Host tool approvals can give the human a chance to intervene at
each send. A host configured to approve calls automatically offers no such
pause. Recipient inbound policy can hold or refuse a letter where the host
provides it. MCP body and page caps, worker-result depth checks and
nonblocking MCP locks remain, as do native transport timeouts. The CLI does
not apply MCP's body cap. These controls do not bound the correspondence.

Ending a Claude process closes its inbox. Closing a Codex client can leave
its persisted thread available for queued letters. Making a ledger unwritable
prevents new write opens of it. Mutations also check the mode after taking
the lock, so an existing waiter may refuse. An operation past that check
may finish, and read access can remain. Postbag does not restore the mode
of an existing file. None of these actions recalls queued letters or cancels
a submission already in flight.

`leave` withdraws one door's registration in one bag. It blocks later sends
to and from that registration until a join makes the door addressable again.
It does not close the native inbox, change registrations in other bags,
recall queued letters or interrupt a send already holding the ledger lock.
Claude subagents sharing an inbox withdraw the same registration. The leave
record preserves its door fields so replay can check the current binding.
This checks consistency, not authenticity against someone who can edit the
ledger. Do not rejoin after a deliberate leave unless the human asks to resume.

## What "delivered" means

`send` reports a letter delivered when it was submitted through the door:
the socket write returned, or `codex queue` exited 0. postbag does not read
delivery notices or wait for an acknowledgement. Submission is not proof the
recipient accepted, read or acted on the letter. A crash between the knock
and the ledger append can leave a submitted letter unrecorded. postbag
provides no acknowledgement, retry or exactly-once guarantee.
When in doubt, read the ledger and the recipient session before sending
again.

## Reporting

Report a suspected vulnerability through this repository's private
vulnerability reporting on GitHub. Include a minimal reproduction with dummy
credentials and the Claude Code, Codex and Python versions. Never include a
live token or a raw ledger.
