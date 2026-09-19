# Security

## What postbag trusts

postbag trusts the local OS account and the sessions that joined the bag.
Who may run each verb is decided by environment variables the vendors export
inside their own sessions: `join` and `send` run inside a session, `open`
runs outside agent sessions. That prevents role mistakes between the human
and the agents. It is not a boundary against another program running as the
same user. A name is an address, not authentication.

## What the ledger holds

Each selected bag, `~/.postbag/ledger.jsonl` by default, a named bag under
`~/.postbag/bags`, or a custom path from `--bag` or `POSTBAG_LEDGER`, holds
every letter body and every registered door: each Codex thread id, and each
Claude messaging socket path and session token. Several doors of one vendor
can be registered. Writes keep the file `0600` and new state directories
`0700`. An existing directory is left alone, whichever selector chose it.
Anyone who can read that file can submit messages to its registered Claude
inboxes. The recipient's policy still governs acceptance.

`postbag read` and `postbag bags` hide door credentials and print registered
names and vendors on purpose. Inventory also shows remaining budgets and
last recorded letter timestamps, but no letter bodies. It reads ledgers
without contacting sessions. Registration does not establish liveness.
`cat` hides nothing. Keep the ledger out of git, issues, logs and screenshots.

## What a letter can do

A letter accepted by the recipient becomes a user turn. Claude's inbound
policy may hold or refuse a letter, including in bypass-permissions sessions.
The [recorded live checks](../docs/native-compatibility.md) observed
unattended delivery. That is an observation, not an exemption from the
recipient's permissions. postbag does not claim a sender permission mode or
change the recipient's policy. The human's letter budget is the brake. When
it is spent, `send` refuses, and only a human outside the agent sessions can
open another exchange. Use postbag only between sessions you would trust
with the same task.

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
