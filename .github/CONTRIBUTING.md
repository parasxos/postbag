# Contributing

Read [CONCEPT.md](../CONCEPT.md) first. It is short and it is the
specification. Four nouns, four verbs, one ledger per bag and native doors.
Agents and their hosts decide when to stop. Any two supported sessions, of
the same vendor or not, are the supported use. Three or more is experimental. A change that adds a noun
has to name the capability the existing nouns cannot provide.

## Develop

```sh
git clone https://github.com/parasxos/postbag.git
cd postbag
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev,mcp]"
python -m pytest -q
```

Tests isolate the default and named-bag directories as well as
`POSTBAG_LEDGER`, and use fake doors. They must never scan the user's bags
or reach a real session. Core tests use the standard library and pytest.
MCP wire tests require the optional `mcp` extra and skip without it.

## Change

- Every refusal goes through `fail()` and ends with "stop and ask the
  human". Tests match on that wording.
- `send` validates arguments, including the final flag and Unicode, before
  taking the ledger lock. Sender and recipient checks, transport and append
  run under the lock.
  A letter record means submission succeeded before recording. A crash can
  leave a submitted letter unrecorded. Recipient permissions still apply.
  Do not claim sender permissions or consume delivery notices.
- `join` creates a missing bag. Argument and identity refusals create nothing.
  Missing-bag `send` and `read` create no files or directories. Preserve any
  partial file after an I/O failure instead of deleting another caller's state.
- Create ledger files as `0600` and preserve existing modes. Refuse mutations
  when an existing file grants group or other access or lacks owner read and
  write. Check the existing mode after acquiring the lock. An operation
  already past that check may finish after a permission change.
- The envelope text in `envelope()` is the protocol the agents follow.
  Change it and its tests together. `final` is a strict Boolean and an advisory
  request not to reply to that letter. It must not disable later explicit sends.
- Never print door credentials. Inventory also excludes letter bodies.
- `bags` adds no state and probes no sessions. It skips waiting on a busy
  ledger, reports unavailable bags, continues the inventory, and exits 1.
- Legacy ledgers must keep reading without rewriting. Historical `open` rows
  retain their limits but do not control sending. Record `n` and paging cursors
  remain unchanged, while letter numbers count all recorded letters in a bag.
- Preserve identity, redaction, uncertain-submission and cancellation tests
  when changing the message flow. Test worker skew with actual old and new
  modules. Do not infer pre-submission failure from an unstructured worker exit.

Commit subjects are short and imperative.

## Release

1. Bump `__version__` in `postbag.py`, finalize the `CHANGELOG.md` entry, and
   pin README links to current documentation at the new tag for PyPI.
   Keep historical examples and evidence linked to their original versions.
   Remove draft notices only when the checks below establish release readiness.
2. CI green on `main`.
3. Native acceptance test, the actual gate: install the release candidate
   in a clean venv and observe a letter received in each direction between
   two real sessions. Then send a final letter and record the recipient's
   behavior over an explicit observation window. Deliberately initiate a later
   ordinary letter and observe its receipt. This checks the candidate's behavior,
   not universal prevention of reply loops. Record the actual session runtime
   versions, OS, recipient permission modes and inbound settings, both
   directions, and whether human approval was needed. Use independent
   sessions and record any native own-child classification. Independence
   alone does not rule out that classification.
   Preserve recipient policy and do not claim sender permissions to make
   delivery pass. Distinguish a submitted letter from one visibly received.
   Keep the evidence in [native compatibility checks](../docs/native-compatibility.md).
   Do not tag until these native checks pass. Historical 1.x checks do not
   establish 2.0 acceptance.
4. `git tag v<version> && git push origin v<version>`. The release
   workflow builds the wheel and sdist, checks them, publishes a GitHub
   release with checksums, then publishes those same assets to PyPI
   through trusted publishing.
