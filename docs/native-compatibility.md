# Native compatibility checks

## 19 September 2026: Claude Code 2.1.278

The unchanged Claude socket transport passed a round trip between two
independent headless Claude Code sessions on macOS 27.0 (build 26A428).
This checks the native receiver and agent execution, not only a fake socket.
It does not extend the historical interactive or Claude–Codex verification
to these versions, and it is not a release verification. Earlier live checks
used Claude Code 2.1.263 and Codex 0.153.4 on macOS, across vendors, between
two Claude sessions, and in a named bag.

Source: `postbag.py` at base commit `678879c`, SHA256
`66bd37b342bfdcba7f8aa88188f2c83848b6119d8829b86215b8d0120a0ea4fc`.
No transport or wire-format change was needed.

### Isolation and procedure

Each native session joined through its own Bash tool, using its exported
socket and token. Test directories were private (`0700`) and ledgers were
`0600`. Ledgers were pre-seeded test fixtures with budgets of one letter per
probe and two for the round trip. Only singleton probes used a synthetic
sender registration, whose door was never contacted. The sessions used
explicit private sockets, no persisted sessions, no user settings or MCP
servers, and these Claude launch options:

```text
--safe-mode --setting-sources '' --strict-mcp-config
--mcp-config <empty configuration> --no-session-persistence
--tools Bash --allowedTools Bash
```

Bash was authorized at launch for the fixture's join and send commands.
No human approval was required during the checks. The sender process stayed
alive during each receiver probe. The messages contained no claimed sender
permission mode, and no personal bag or existing session was contacted.

Both round-trip sessions used normal prompting mode (`manual` at the CLI),
with `crossSessionInbound` unset. A unique challenge arrived through the
first native inbox, and its exact reply arrived through the other. The
final-letter envelope was observed. A third send refused after the budget
was spent, with the ledger unchanged and no transport call.

### Recipient policy probes

Separate sibling-process probes submitted letters to real Claude inboxes:

| Recipient mode | `crossSessionInbound` | Observation |
|---|---|---|
| Normal prompting (`manual` at CLI) | Unset | Letter accepted and echoed. |
| Bypass permissions | Unset | Letter accepted and echoed. The native receiver marked the origin `selfSent=true`. |
| Bypass permissions | `accept` | Letter accepted and echoed. |
| Bypass permissions | `hold` | Native `peer_message_hold` notice with reason `explicit-setting`. |
| Bypass permissions | `refuse` | Native receiver log confirmed refusal. Submission and ledger recording succeeded, no letter echo appeared, and a direct PING was answered. |

The bypass/unset result does not establish acceptance of an origin that
Claude identifies as external. It records the receiver's observed origin
classification, despite the probe running in a sibling process. The refuse
row was confirmed by this fixed line in the native receiver's debug log:

```text
[cross-session-inbound] refused inbound peer message (uds: dropped before attachment materialization)
```

The accepted letters were processed before the direct PING. The refusal
probe also preserved the ledger hash when a further send met the spent budget.

### Consequence for postbag

The native fields and wire format still work in this test. Recipient policy
can hold or refuse a submitted letter. A successful socket write and ledger
entry do not establish acceptance. postbag does not read native delivery
notices, retry, claim sender permissions, or change the recipient's policy.

For a future native check, record the actual session runtime versions and
policy, not just the executable currently installed. Preserve the distinction
between submission, native receipt, and the recipient's visible response.

## 20 September 2026: recorded conversation resume

An isolated, persisted Claude Code 2.1.278 session ran `join claude reader`
through its own Bash tool. The join's optional `session_id` matched the
native result's conversation ID. `bags --resume` printed that exact UUID
without changing the ledger. Its command, run headlessly from a different
directory after the first process exited, reopened the same conversation
and recalled its unique test phrase exactly. No letters were sent.

This verifies capture and cross-project resume for saved history. It does
not establish that every recorded conversation still exists, or that the
conversation at join remains current after `/clear` or an in-process switch.
