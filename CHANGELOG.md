# Changelog

All notable changes to postbag are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/).

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

[1.0.0]: https://github.com/parasxos/postbag/releases/tag/v1.0.0
