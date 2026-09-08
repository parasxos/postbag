# Changelog

All notable changes to postbag are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- `SECURITY.md` and `CONTRIBUTING.md` moved to `.github/`, where GitHub
  still discovers them. The root holds README, CONCEPT and CHANGELOG.

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

[Unreleased]: https://github.com/parasxos/postbag/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/parasxos/postbag/releases/tag/v1.0.1
[1.0.0]: https://github.com/parasxos/postbag/releases/tag/v1.0.0
