# Contributing

Read [CONCEPT.md](../CONCEPT.md) first. It is short and it is the
specification. Five nouns, five verbs, one ledger per bag, native doors, a human
sets the budget. Any two supported sessions, of the same vendor or not, are
the supported use. Three or more is experimental. A change that adds a noun
has to name the capability the existing nouns cannot provide.

## Develop

```sh
git clone https://github.com/parasxos/postbag.git
cd postbag
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q
```

Tests isolate the default and named-bag directories as well as
`POSTBAG_LEDGER`, and use fake doors. They must never scan the user's bags
or reach a real session. Keep them fast and stdlib-only.

## Change

- Every refusal goes through `fail()` and ends with "stop and ask the
  human". Tests match on that wording.
- `send` does budget, knock, then append, all under the ledger lock. A
  letter exists iff it was delivered and then recorded.
- The envelope text in `envelope()` is the protocol the agents follow.
  Change it and its tests together.
- Never print door credentials. Inventory also excludes letter bodies.
- `bags` adds no state and probes no sessions. It skips waiting on a busy
  ledger, reports unavailable bags, continues the inventory, and exits 1.
- Legacy ledgers must keep reading.

Commit subjects are short and imperative.

## Release

1. Bump `__version__` in `postbag.py`, add a `CHANGELOG.md` entry, and
   move the tag-pinned links in `README.md` to the new tag.
2. CI green on `main`.
3. Native acceptance test, the actual gate: install the release candidate
   in a clean venv and run one two-way exchange between two real sessions,
   including the spent-budget refusal. Do not tag until it passes.
4. `git tag v<version> && git push origin v<version>`. The release
   workflow builds the wheel and sdist, checks them, publishes a GitHub
   release with checksums, then publishes those same assets to PyPI
   through trusted publishing.
