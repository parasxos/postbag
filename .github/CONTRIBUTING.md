# Contributing

Read [CONCEPT.md](../CONCEPT.md) first. It is short and it is the
specification. Two peers, four verbs, one ledger, native doors, a human
sets the budget. A change that adds a noun has to name the capability the
existing nouns cannot provide.

## Develop

```sh
git clone https://github.com/parasxos/postbag.git
cd postbag
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q
```

Tests use a temporary `POSTBAG_LEDGER` and fake doors. They must never
reach a real session. Keep them fast and stdlib-only.

## Change

- Every refusal goes through `fail()` and ends with "stop and ask the
  human". Tests match on that wording.
- `send` does budget, knock, then append, all under the ledger lock. A
  letter exists iff it was delivered and then recorded.
- The envelope text in `envelope()` is the protocol the agents follow.
  Change it and its tests together.
- Never print a door field other than the peer name.
- Legacy ledgers must keep reading.

Commit subjects are short and imperative.

## Release

1. Bump `__version__` in `postbag.py` and add a `CHANGELOG.md` entry.
2. CI green on `main`.
3. `git tag v<version> && git push origin v<version>`. The release
   workflow builds the wheel and sdist, checks them, publishes a GitHub
   release with checksums, then publishes those same assets to PyPI
   through trusted publishing.
4. Install from the tag in a clean venv and run one two-way exchange with
   real sessions, including the spent-budget refusal.
