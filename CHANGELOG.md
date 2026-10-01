# Changelog

All notable changes to postbag are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `postbag mcp` starts the existing stdio MCP server without changing the
  five bag operations. It takes no bag option or operational arguments and keeps
  the same optional MCP dependency and missing-extra guidance.
- MCP Registry metadata and release automation, with a pinned uvx launch
  command that installs the MCP extra from the same package version.
- Agent installation instructions, marketplace artwork and a current CLI
  demo using temporary state and fake native doors.

### Changed
- Refresh the README with direct installation, MCP setup and supported-host
  information. Directory publication and tool introspection do not establish
  native message delivery or expand the supported peers.

## [2.1.0] - 2026-10-01

Leaving a bag is now a recorded withdrawal of the caller's name. MCP
inventory also reports the installed worker version. Upgrade both peers,
including their CLI and MCP installations, and reconnect each MCP server.
Bags containing a leave record require 2.1 readers. Older bags remain
unchanged and need no migration.

### Added
- CLI `leave` and MCP `postbag_leave` withdraw the caller's current name
  from one bag. They preserve its history and session, contact no native
  transport, and append a leave record under the same lock as sending.
  Queued letters can still arrive. Rejoin only when the human asks to resume.
- MCP inventory data includes `version` for the installed core loaded by
  that call's worker, including empty and partial inventories. It does not
  prove that the running parent has refreshed its tool catalog.

### Changed
- Preserve the core refusal reason when directing an MCP caller to read
  the bag, including departure times and names that moved to another door.

### Compatibility
- Upgrade every reader of a bag before recording its first leave. Readers
  older than 2.1 refuse a bag containing that record. Existing bags need no
  rewrite. Downgrading does not undo a leave, and deleting leave rows would
  restore withdrawn registrations. Unknown record kinds remain errors.
- Reconnect MCP servers after upgrading to expose the new tool. The internal
  worker protocol remains 2 and does not negotiate tool availability.

## [2.0.0] - 2026-10-01

Postbag no longer uses letter budgets or exchanges. Upgrade both peers,
including their CLI and MCP installations, and reconnect each MCP server.
Existing bags read without migration. Historical `open` records remain as
inert history.

### Removed
- Remove the `open` command, exchanges, letter budgets and the human-only
  command distinction. Postbag sets no limit on the number or rate of letters.
- Remove derived exchange and remaining-budget fields from MCP results.

### Added
- CLI `send --final` and MCP `final=true` ask for no reply to that letter.
  The flag is a strict Boolean, absent meaning false. It is stored in the
  ledger only when true and returned in send receipts and MCP letter records.
  Its footer carries no reply command. It does not prevent a later send.
- Internal worker protocol 2 uses a separate entry point. Old-server/new-worker
  mismatch refuses before work. New-server/old-worker mismatch exits before
  dispatch, but the parent conservatively reports an unknown send outcome
  because an unstructured exit cannot prove that stage. Reconnect after
  upgrading or downgrading. There is no fallback to the old entry point.

### Changed
- `join` creates a missing default, named or path-selected bag. Argument and
  identity refusals create nothing. Missing-bag `send` and `read` create no
  files or directories and direct the caller to `join` or `bags`, respectively.
  Once creation starts, an I/O failure can leave a directory or partial file.
- Count letters cumulatively across each bag. Inventory reports letter counts
  instead of budgets, and distinguishes bags with letters, bags without letters
  and unavailable bags.
- Ask recipients to reply only when doing so advances the task, without
  courtesy acknowledgements, unsolicited delivery checks or unnecessary
  questions. Human-requested receipts remain substantive work.
- Preserve existing ledger modes. Mutations refuse files with group or other
  access or without owner read and write. Only creation sets mode `0600`.
- Keep MCP's body, page and worker-result depth caps and nonblocking locks,
  along with native transport timeouts. The CLI does not apply MCP's body
  cap. These resource controls do not prevent reply loops.

### Compatibility
- Read historical bags without rewriting. Retain old `open` rows and their
  `limit` as inert history. Every record keeps its original `n`, addressed by
  MCP `before` and `next_before`. CLI `read N` returns the last N records.
  Displayed letter numbers count only letters, including those before old
  exchange boundaries.
- Mixed 1.x/2.0 participants are unsupported and not negotiated. An old sender
  still applies the last retained budget and counts 2.0 letters against it.
  New bags have no `open` row, so old senders refuse there. Old readers hide
  the final flag. Upgrade all participants before continuing.
- Footer guidance, final flags and host approvals do not guarantee that models
  stop. Closing a client does not revoke a persisted queue or recall a letter.
  Mutations check existing ledger modes after taking the lock. If a ledger
  becomes unwritable, a waiting mutation can refuse, while an operation past
  that check may finish and read access can remain.

### Validation
- The installed `8b87b4f` candidate passed native acceptance on its first run:
  two-way receipt, a 30.0668-second final-letter observation and a deliberately
  initiated ordinary round trip afterward. [Native evidence](docs/native-compatibility.md)
  records exact provenance, runtime versions, permissions and limits.
- The same candidate passed 586 full-suite tests, 157 installed-wheel MCP
  tests and 55 extracted-sdist `test_core_2.py` checks. All 13 CI jobs passed.
  [Candidate CI](https://github.com/parasxos/postbag/actions/runs/36842969085).

## [1.4.0] - 2026-10-01

Refusals now carry structured recovery guidance, so an MCP caller is told
which tool to call and who must act, and the envelope names the MCP send
tool for named and default bags. The native queue subprocess no longer
inherits the sender's inbox fields. Upgrade both peers to the same version
and reconnect their MCP servers. Existing ledgers need no migration.

### Fixed
- Name MCP tools in recovery guidance and reply instructions for default and
  named bags. Path-based bags keep their CLI reply command. Recovery identifies
  whether the caller, recipient, or human must act.
- Reject malformed Unicode before CLI submission while preserving legacy
  ledger reads. Handle oversized JSON integers as clean ledger refusals.
- Report uncertain recording after a flush or fsync failure without claiming
  that the submitted letter is absent from the ledger.
- Preserve structured unknown outcomes for malformed or excessively nested
  worker responses. Warn shared-inbox subagents before they rename a peer.
- Remove sender inbox and identity fields from the native queue subprocess
  environment. Private fixtures verify this filtering, and a live cross-vendor
  exchange with the installed candidate confirmed native delivery.

### Changed
- Expand failure and cancellation regression coverage, isolate CLI test homes,
  and test MCP against an installed wheel outside the source checkout.
- Clarify partial inventory results, recorded-letter budget limits, and
  full-suite dependency requirements.

## [1.3.0] - 2026-09-30

MCP tools remove shell-command friction while retaining the existing bag,
native transports, and human-controlled letter budget. Upgrade both peers
to the same version, reconnect their MCP servers, and rejoin under the
same names. Existing ledgers and remaining budgets need no migration.

### Added
- Optional `postbag[mcp]` extra and `postbag-mcp` stdio entry point with four
  tools: join, send, read, and bag inventory. Budgets remain human-controlled.
  Tools bind native caller identity, accept named bags, return structured
  outcomes, and isolate each invocation in a subprocess.
- MCP wire tests for current and legacy clients, sender binding, private
  socket delivery, concurrency, budget limits, pagination, and cancellation.
- Installed-package native acceptance with Claude Code 2.1.285 and Codex
  0.157.1 / desktop 0.158.0-alpha.2.1, including default server discovery,
  model-authored replies, observed receipt, and spent-budget refusal.
  Live Claude `/clear`, native Linux delivery and restricted spawned-agent
  targets remain unverified. Forced process-tree termination can leave an
  unknown submission outcome.
- `postbag bags --resume` shows Claude resume commands using optional conversation
  IDs recorded at `join`. These snapshots do not change door identity or routing.
  Older or invalid metadata gets one rejoin reminder after the inventory.
  Known IDs add one copyable command per peer beneath the bag's ordinary row.
- `postbag bags`, a read-only inventory with a count of discovered paths, remaining budget,
  last recorded letter timestamp, and registered names with vendors.
- Scan the default ledger and valid named ledgers directly under
  `~/.postbag/bags`, plus an explicitly selected existing custom path.
  Unselected external paths cannot be discovered. A selected custom alias
  of an already listed regular file is not repeated.
- Unavailable ledgers remain in the count. Busy or unreadable ledgers and scan
  errors do not hide other readable bags. The command reports them and exits 1.
  It creates no files or index, probes no sessions, and changes no ledger format.
  Budgets do not expire, and registered names do not imply live sessions.
- Terminal inventory adapts to width, groups peers by vendor and orders bags
  by their last recorded letter. It uses brief local times and optional styling.
  Piped output keeps the original table, order and full ISO timestamps.
  `NO_COLOR` or `TERM=dumb` disables terminal styling.

### Changed
- Report uncertain native submissions without advice to blindly resend.
  Timeouts, partial socket writes, and nonzero queue exits may have delivered.
  Recording failures preserve the fact that native submission succeeded.
- Keep `bags --resume` in the ordinary compact inventory layout. Show missing-ID
  guidance once and brighten secondary terminal text for readability.
- Clarify that postbag records submission, does not read delivery notices,
  and does not guarantee recipient acceptance. Claude's inbound policy may
  hold or refuse a letter even in a bypass-permissions session.
- Record runtime versions and recipient policy in native acceptance checks,
  distinguishing live receipt from successful submission.
- Verify the unchanged native transport between two headless Claude Code
  2.1.278 sessions on macOS, with separate recipient-policy probes.

### Fixed
- Prefer the concrete `CODEX_THREAD_ID` over the shared root's
  `CODEX_SESSION_ID`, keeping the latter as a fallback for older hosts.
  Existing peers whose thread differs from that shared ID need to join again.
- Refuse NUL-containing messages and oversized native command arguments with
  actionable errors before submission.
- Render stored timestamps in canonical form so legacy timestamp separators
  cannot inject terminal controls.

## [1.2.1] - 2026-09-09

Documentation release. No runtime change beyond the version number.

### Changed
- The README is a manual again: the upgrade notes and the release-by-release
  verification history moved out, this file keeps them. One sentence remains,
  both sessions run the same postbag.

## [1.2.0] - 2026-09-09

A bag has a name. Named bags let two conversations use separate ledgers,
nothing is separated automatically, and every command an agent is handed
says which bag it belongs to.

### Added
- Named bags. `default` is `~/.postbag/ledger.jsonl`, any other name is
  `~/.postbag/bags/<name>.jsonl`, and an absolute path is a bag too. A bag
  name follows the peer name grammar, and `default` is reserved.
- `--bag NAME` before every verb: `postbag --bag acceptance read`. It
  overrides `POSTBAG_LEDGER`, and a bare command selects as before.
- `open` creates a named bag that does not exist. `join`, `send` and `read`
  refuse one and say which command the human should run.
- Every success line, every refusal after bag selection and every envelope
  names the bag, `default` included: "@bob (claude) joined in bag default",
  "exchange open: 12 letters in bag acceptance", "in bag acceptance: @ada
  (claude), @bob (claude). exchange 3: 8 of 12 letters left." The constant
  refusal of an invalid path carries no bag label.
- Every command postbag generates carries the bag: the reply command in a
  letter, the `join` a refusal asks a restarted session to run, the `open`
  it asks the human for, and the `read` it points to. An absolute path is
  single-quoted for the shell.

### Changed
- The envelope's first line is "Letter 4 of 12 from @ada to @bob via
  postbag (exchange 3, bag acceptance)", for the last letter too.
- The reply command inside a non-final letter is
  `postbag --bag acceptance send @ada -`.
- `join`, `open`, `send` and `read` name the bag on their first line:
  "letter 4 of 12 in exchange 3 delivered to @bob in bag acceptance, 8 left".

### Compatibility
- The ledger format is unchanged. Old ledgers read without rewriting, and
  no version gate was added.
- A 1.1 `send` refuses `--bag`, which every 1.2 reply command carries, so
  scoped commands need 1.2 at both ends, the default bag included. An older
  CLI reaches a bag by path: `POSTBAG_LEDGER='/abs/path' postbag send ...`.
- `POSTBAG_LEDGER` is unchanged: a path, `~` expanded, used when `--bag` is
  absent.
- A ledger path must contain only printable characters. A custom path
  holding a control character or a line separator is now refused.

## [1.1.1] - 2026-09-09

### Fixed
- `read` exits quietly when its reader closes the pipe early.

## [1.1.0] - 2026-09-09

Any two sessions, of the same vendor or not. The nouns and verbs are the
same five and four, and the words now match Claude Code's own.

### Added
- Named doors: `join` records the session's door under a name, by default
  the vendor. A name is a lowercase letter followed by up to fifteen
  lowercase letters, digits or hyphens. `claude` and `codex` are reserved
  for doors of that vendor. The last `join` wins both ways, and `join` says
  what it renamed or took.
- Any two sessions can correspond, two Claude Code sessions included. The
  sender is the door the shell runs in, matched against exactly one
  registered name. There is still no `--from`.
- `send @name`, with or without the `@`. A send to a name nobody holds
  refuses and points to `read`, and, when the last door to hold it now
  holds another name, says which.
- Letters are numbered within their exchange. Each `open` starts the next
  exchange and closes the one before it.
- `read` begins with one line: the names the bag holds now, each with its
  vendor, and the open exchange. Records are grouped by exchange, and joins
  carry a note when they renamed a door or took a name.
- The envelope names the exchange, "Letter 4 of 12 from @ada to @bob via
  postbag (exchange 3)", says the budget is shared by everyone in the bag,
  and lists the registered names when the bag holds more than two.
- CONCEPT.md gains a table mapping Claude Code's words, `SendMessage` and a
  session's name, onto postbag's.

### Changed
- `join` takes a vendor and an optional name: `postbag join claude ada`.
- The reply command inside a non-final letter is `postbag send @name -`.
  The last letter of an exchange carries none and says not to reply.
- CLI output and refusals never carry door credentials, and only
  ledger-integrity refusals name a ledger line.
- Argument errors end the same way every refusal does: stop and ask the
  human. A truncated ledger's refusal names the last complete line and asks
  you to inspect the last record before repairing the file.
- `open --help` and `read --help` describe their arguments, and the default
  budget of 12 letters is stated.

### Compatibility
- Ledgers written by 1.0 read without rewriting. Legacy vendor peers read
  as `@claude` and `@codex`.
- A 1.0 session cannot answer a 1.1 letter, since its `send` takes only
  `claude` or `codex`. Upgrade both sessions, then ask each to `join` again.
- A third door in the bag is experimental. `read` says so, the budget is
  shared, and nothing more is promised.

## [1.0.2] - 2026-09-08

Documentation release. No runtime change beyond the version number.

### Changed
- `SECURITY.md` and `CONTRIBUTING.md` moved to `.github/`, where GitHub
  still discovers them. The root holds README, CONCEPT and CHANGELOG.
- README links are pinned to the release tag, so the description PyPI
  keeps for each version never points at a moved file.

## [1.0.1] - 2026-09-08

Documentation release. No runtime change beyond the version number.

### Added
- postbag is on PyPI: `pipx install postbag`. The release workflow publishes
  the GitHub release assets through trusted publishing, and
  `workflow_dispatch` with a tag publishes an existing release.
- A recorded demo, `docs/assets/demo.gif`, made by `vhs docs/demo.tape`
  against fake doors in `docs/demo-env.sh`. The tape and harness ship in
  the source archive.
- `docs/readme-research.md`: what current tool READMEs do, and the
  neighbouring tools for agent-to-agent messaging on one machine.

### Changed
- The README is a third of its former length, with no emoji, two badges,
  absolute links for PyPI, capability checks and tested vendor versions,
  and a link to the landscape research.

## [1.0.0] - 2026-09-08

First public release. Two agents on one machine, a Claude Code session and
a Codex session, correspond by letters through each vendor's own door.

### Added
- `postbag.py` as an installable module with a `postbag` console command.
  `pipx install git+https://github.com/parasxos/postbag@v1.0.0`.
- `postbag --version`.
- Ledger records are validated on every read: kind, sequence number, peers,
  door fields, budget. A bad line is refused by number.
- The ledger directory is created `0700` and the file kept `0600`, since the
  Claude session token lives in it. Appends are flushed and fsynced.
- Reads take a shared lock, writes an exclusive one, so concurrent sends
  get distinct numbers and one budget.
- Timestamps carry a UTC offset.
- The Codex binary is found through `POSTBAG_CODEX`, then the ChatGPT app
  bundle on macOS, then `codex` on `PATH`.
- MIT license, changelog, security policy, contributing guide, CI on
  macOS and Linux for Python 3.10 to 3.14, release workflow on `v*` tags.

### Changed
- The reply instruction inside every letter now uses the heredoc delimiter
  `POSTBAG` and tells the reader to pick one that does not occur in the reply.
- A refusal because a door did not answer names the `join` command the
  recipient must run again.
- The checked-in `postbag` executable is a thin wrapper around `postbag.py`,
  so a symlink to a checkout keeps working.

### Unchanged by design
- Two peers, four verbs, one ledger, no daemon, no polling, no hooks, no
  configuration file. See [CONCEPT.md](CONCEPT.md).
- Legacy ledgers written before 1.0.0 still read.

## [0.x] - 2026-09-08

Four commits from "bridge" to "postbag" on the day the idea was born:
the ledger became the only state, `open` became human-only, and every
refusal learned to say stop.

[Unreleased]: https://github.com/parasxos/postbag/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/parasxos/postbag/releases/tag/v2.1.0
[2.0.0]: https://github.com/parasxos/postbag/releases/tag/v2.0.0
[1.4.0]: https://github.com/parasxos/postbag/releases/tag/v1.4.0
[1.3.0]: https://github.com/parasxos/postbag/releases/tag/v1.3.0
[1.2.1]: https://github.com/parasxos/postbag/releases/tag/v1.2.1
[1.2.0]: https://github.com/parasxos/postbag/releases/tag/v1.2.0
[1.1.1]: https://github.com/parasxos/postbag/releases/tag/v1.1.1
[1.1.0]: https://github.com/parasxos/postbag/releases/tag/v1.1.0
[1.0.2]: https://github.com/parasxos/postbag/releases/tag/v1.0.2
[1.0.1]: https://github.com/parasxos/postbag/releases/tag/v1.0.1
[1.0.0]: https://github.com/parasxos/postbag/releases/tag/v1.0.0
