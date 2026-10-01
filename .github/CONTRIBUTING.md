# Contributing

Read [CONCEPT.md](../CONCEPT.md) first. It is short and it is the
specification. Four nouns, five verbs, one ledger per bag and native doors.
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
  Missing-bag `send`, `leave` and `read` create no files or directories. Preserve any
  partial file after an I/O failure instead of deleting another caller's state.
- Create ledger files as `0600` and preserve existing modes. Refuse mutations
  when an existing file grants group or other access or lacks owner read and
  write. Check the existing mode after acquiring the lock. An operation
  already past that check may finish after a permission change.
- The envelope text in `envelope()` is the protocol the agents follow.
  Change it and its tests together. `final` is a strict Boolean and an advisory
  request not to reply to that letter. It must not disable later explicit sends.
- Never print door credentials. Inventory also excludes letter bodies.
- `leave` withdraws the caller's current name under the same lock as `send`.
  It creates nothing and contacts no native door. Replay requires that the
  named peer is still held by the recorded identity. Leave rows retain record
  numbers but do not count as letters. Queued letters do not authorize rejoining.
- `bags` adds no state and probes no sessions. It skips waiting on a busy
  ledger, reports unavailable bags, continues the inventory, and exits 1.
- Legacy ledgers must keep reading without rewriting. Historical `open` rows
  retain their limits but do not control sending. Record `n` and paging cursors
  remain unchanged, while letter numbers count all recorded letters in a bag.
- Preserve identity, redaction, uncertain-submission and cancellation tests
  when changing the message flow. CI keeps compact worker-protocol fixtures.
  Before a major worker-protocol change ships, also test actual old and new
  modules. Do not infer pre-submission failure from an unstructured worker exit.

Commit subjects are short and imperative.

## Release

1. Bump `__version__` in `postbag.py`, finalize the `CHANGELOG.md` entry, and
   pin README links to current documentation at the new tag for PyPI.
   Match `server.json`'s server version, PyPI package version, and
   `postbag[mcp]==<version>` runtime argument to that version. Keep the
   Dockerfile's `ARG POSTBAG_VERSION` on that version too. Preserve the
   `mcp-name: io.github.parasxos/postbag` ownership marker in the README that
   goes into the distribution. The registry checks the published PyPI
   description, not the repository's current README.
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
   For 2.1, observe a leave between two deliveries: A sends to B, B leaves,
   A's next send refuses with the departure time, B deliberately joins again,
   and A's next send is visibly received. Observe a reply in the other direction.
   Also test both actual 2.0/2.1 parent and worker pairings, and confirm that a
   2.0 reader cleanly refuses a bag containing a leave. Fixture tests must
   not stand in for these installed-version checks.
   Do not tag until these native checks pass. Historical 1.x checks do not
   establish 2.0 acceptance, and 2.0 checks do not establish 2.1 acceptance.
   For 2.2, run the clean installed candidate through `postbag mcp`, confirm
   its tool catalog matches `postbag-mcp`, and perform the two-way, final,
   and later ordinary letter checks above through that launcher. Successful
   initialization alone does not establish native acceptance.
4. `git tag -a v<version> -m "Release <version>"` then
   `git push origin v<version>`. The release
   workflow builds the wheel and sdist, checks them, publishes a GitHub
   release with checksums, then publishes those same assets to PyPI
   through trusted publishing. After PyPI succeeds, it registers the tagged
   `server.json` in the official MCP Registry through GitHub OIDC.

### Registry publication and retries

The registry entry uses the PyPI identifier `postbag`, with `uvx` as its
runtime. `--with postbag[mcp]==<version>` installs the optional MCP
dependencies, and the package argument `mcp` starts the stdio server. A
client must preserve those runtime and package arguments when constructing
the launch command. Extras do not belong in the registry's PyPI identifier.
See the [registry package rules](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/package-types.mdx)
and [uv tool requirements](https://docs.astral.sh/uv/concepts/tools/#including-additional-dependencies).

The release job verifies tag, package, and registry versions before
registering. It waits for the versioned PyPI API to expose both distributions
and the README ownership marker. Transient failures get at most 12 attempts,
with 10 seconds between requests and a 10 second request timeout. A missing
ownership marker or version mismatch stops immediately. Registration itself
runs once, so a timeout does not silently trigger another publication.

If PyPI succeeded but registration failed, inspect the
[registry entry](https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.parasxos/postbag)
and the workflow logs before retrying. A failed or interrupted publication
can have reached the registry. Confirm the exact version and metadata, not
just the search result's latest entry. To retry only registration, dispatch
the Release workflow with the existing `vX.Y.Z` tag and `registry_only: true`.
This reads `server.json` from that tag and skips another PyPI upload. Leaving
the option false publishes an existing GitHub release's assets to PyPI first.
Do not reuse that mode for a version already uploaded to PyPI.

The registry job has only `contents: read` and `id-token: write` permissions.
It uses the official publisher pinned to version 1.8.1 and a checked SHA-256
archive digest. When changing that pin, verify the digest against the
[official release](https://github.com/modelcontextprotocol/registry/releases/tag/v1.8.1),
review its OIDC behavior, and test the workflow without logging in or
publishing. The token is removed from the ephemeral runner after the attempt.
GitHub release, PyPI publication, and registry registration are separate
outcomes. Confirm all three before reporting a fully listed release.
