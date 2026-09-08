# Security

## What postbag trusts

postbag trusts the local OS account and the two sessions that joined. Who
may run each verb is decided by environment variables the vendors export
inside their own sessions. That prevents role mistakes between the human,
Claude and Codex. It is not a boundary against another program running as
the same user.

## What the ledger holds

`~/.postbag/ledger.jsonl` holds every letter body, the Codex thread id, the
path of the Claude messaging socket and the Claude session token. postbag
creates the directory `0700` and keeps the file `0600`. Anyone who can read
that file can write user turns into the Claude session while it runs.

`postbag read` never prints door fields. `cat` does. Keep the ledger out of
git, issues, logs and screenshots.

## What a letter can do

A letter arrives in the recipient session as a user turn. In a Claude Code
session running with bypass permissions it is acted on without a prompt.
The human's letter budget is the brake: when it is spent, `send` refuses,
and only a human outside both sessions can open another exchange. Use
postbag only between sessions you would trust with the same task.

## What "delivered" means

`send` reports a letter delivered when it was submitted through the door:
the socket write returned, or `codex queue` exited 0. Neither door sends an
acknowledgement. Submission is not proof the agent read or acted on it. A crash between the knock and the ledger append
can leave a delivered letter unrecorded. There is no acknowledgement,
retry or exactly-once guarantee. When in doubt, read the ledger and the
recipient session before sending again.

## Reporting

Report a suspected vulnerability through this repository's private
vulnerability reporting on GitHub. Include a minimal reproduction with dummy
credentials and the Claude Code, Codex and Python versions. Never include a
live token or a raw ledger.
