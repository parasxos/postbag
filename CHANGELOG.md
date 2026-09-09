# Changelog

All notable changes to postbag are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/).

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

[1.2.0]: https://github.com/parasxos/postbag/releases/tag/v1.2.0
[1.1.1]: https://github.com/parasxos/postbag/releases/tag/v1.1.1
[1.1.0]: https://github.com/parasxos/postbag/releases/tag/v1.1.0
[1.0.2]: https://github.com/parasxos/postbag/releases/tag/v1.0.2
[1.0.1]: https://github.com/parasxos/postbag/releases/tag/v1.0.1
[1.0.0]: https://github.com/parasxos/postbag/releases/tag/v1.0.0
