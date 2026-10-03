# Native compatibility checks

## 3 October 2026: installed 2.3.0 release candidate

A clean wheel built independently from archive
`472556001a861e091b04493aa2c8321420a3766a` passed the native gate on its first
execution. Both fresh hosts used the installed `postbag mcp` launcher from
one isolated venv. Package and runtime versions were `2.3.0`. Installed
modules matched the archive and wheel and remained unchanged throughout.

The run used macOS **27.0.1**, build **26A434**, Python **3.14.6** and MCP SDK
**2.3.0**. Codex CLI **0.159.0-alpha.12.1** reported `gpt-6.1-sol`. Claude
Code **2.1.288** reported `claude-fable-5-1`. The unwrapped native
`codex queue` used default discovery in a private `CODEX_HOME` and reached
a disposable persisted thread. No `--remote` override or queue wrapper was
used. Personal daemon routing and native Linux delivery were not tested.

| Check | Observed result |
|---|---|
| Ordinary delivery | Both sessions received the initial letter and reply, then a later ordinary exchange after rejoining. The two reply turns were created through the native queue, separate from direct harness prompts. |
| Peer guidance | Both Codex incoming reply envelopes contained the new authorization reminder before their unchanged bodies. All five successful send receipts stated that acceptance and execution were unconfirmed. |
| Final letter | After receipt and recipient turn completion, 30.1292 seconds passed with no recipient send attempt or ledger change. Both hosts stayed alive. |
| Leave and refusal | MCP leave withdrew the recipient. The next send returned `refused` and `not_submitted`, included the departure time and preserved the ledger bytes. The recipient did not report receiving its body. |
| Deliberate rejoin | A later explicit harness instruction caused rejoining, after which the ordinary round trip succeeded. |
| Accounting | Ten model-authored calls produced three joins, one leave and five submitted letters. One of the six send attempts refused. Nine record numbers and five letter ordinals were contiguous. |
| Cleanup | Both clients and the private server exited 0 without forced shutdown. Native endpoints closed and the private authentication alias was removed. |

An independent audit checked 69 assertions against raw events, ledger records
and candidate files. Claude's event stream did not expose its inbound envelope
text. Its exact-body stdout receipt markers followed by completed peer-origin
turns corroborated receipt. Those markers were harness instrumentation, not
Postbag replies.
The new guidance was checked as received text in Codex, not as an enforced
authorization boundary or a test of model resistance to contrary instructions.
The final-letter window describes this run, not general loop prevention or
an isolated test of the footer. Leave did not test recall of queued letters.

The command sandbox reported read-only access, disabled network access and
`approvalPolicy: never`. Claude was launched with `--permission-mode manual`
and reported `permissionMode: default`. Preauthorized fixture tools required
no human prompt. `crossSessionInbound` was unset with empty Claude setting
sources. Native own-child classification was unobserved. No personal
configuration or installation changed. Claude used its existing login and
could write its usual caches or telemetry.

The prior 2.2.2 harness was recovered from its recorded source with an exact
SHA256 match. The adaptation selected 2.3.0 and added the guidance and receipt
checks above. Existing native delivery, final-window, leave, rejoin and
cleanup checks were retained.

Candidate provenance:

```text
wheel          d5067840bb710b9fccaa323790dda8de99f18589f613baf70f47c2f1fd1d621c
postbag.py     2f5cbf04d0b6e05a308466c8e45857482050406f05257400931347d285152f5c
postbag_mcp.py f35766d4053051203048f301bee2bc7f2b76fd1864c940f1add09c3390133f25
harness        91d9d9b6ccd03ac65b315d31972d8cedb65bef9e6c712350ed9eb240081ee25d
```

## 2 October 2026: installed 2.2.2 release candidate

An independently built wheel from a clean archive of
`94ad0853ff1a80014954d0972fce2adc4aa00eb2` passed the full native gate on its
first execution. Both fresh hosts used the installed `postbag mcp` launcher
from one isolated venv. Package and runtime versions were `2.2.2`. Installed
modules matched the source and wheel and stayed unchanged. Both launchers
exposed identical five-tool catalogs with current and legacy SDK clients,
and all four checks returned an empty private inventory.

The run used macOS 27.0.1, build 26A434, Python 3.14.6 and MCP SDK 2.2.0.
Codex CLI **0.159.0-alpha.12.1** reported `gpt-6.1-sol`. Claude Code
**2.1.287** reported `claude-opus-5-5`. The unwrapped native `codex queue`
used default discovery in a private `CODEX_HOME`, without `--remote`, and
reached a disposable persisted thread. Personal daemon routing and native
Linux delivery were not tested.

| Check | Observed result |
|---|---|
| Ordinary delivery | Both sessions received the initial letter and reply. The two incoming reply turns were created by the native queue, separate from direct harness prompts. |
| Final letter | After recipient receipt and turn completion, 30.0605 seconds elapsed with no send attempt or ledger change. Both hosts stayed alive. |
| Leave and refusal | MCP leave withdrew the recipient. The next send returned `refused` and `not_submitted`, included the departure time and preserved the ledger bytes. Its body was not received. |
| Deliberate rejoin | An explicit later harness instruction caused rejoining. A later ordinary letter and reply were both received. |
| Accounting | Ten model-authored calls produced three joins, one leave and five submitted letters. One additional send attempt was refused. Nine records and five letter ordinals were contiguous. |
| Cleanup | Both clients and the private server exited 0 without forced shutdown. Native endpoints closed and the private authentication alias was removed. |

An independent audit checked 52 assertions against raw tool events,
recipient turns, timestamps, ledger records and installed files. Claude's
inbound envelopes were not exposed by its event stream. Its exact-body
stdout receipt markers followed by completed peer-origin turns corroborated
receipt. Those markers were harness instrumentation, not Postbag replies.
The final window is evidence for this run, not general loop prevention or
an isolated test of the footer. Leave did not test recall of queued letters.

The command sandbox reported read-only access, disabled network access and
`approvalPolicy: never`. Claude was launched with `--permission-mode manual`
and reported `permissionMode: default`. Preauthorized fixture tools required
no human prompt. `crossSessionInbound` was unset with empty Claude setting
sources. Native own-child classification was unobserved. No personal
configuration or installation changed. Claude used its existing login and
could write its usual caches or telemetry.

Candidate provenance:

```text
wheel          fd98de343c5d4089d27e9b39a80621085e224ffe4b8bebd55ab512cb5706c9d7
postbag.py     18d76fb0643504e381c4bf880bc9b177b8b2e98beff88c2c0d74132f86cc780c
postbag_mcp.py fe354cca37c92c6ce1e5ceaba71a37f0218542834124b1b31ee7528b7f4113c8
harness        bc30165fca08928a4f959ee22465d0beab5ac8c1ccd82e4676d9f3bcaa9fcc71
```

## 2 October 2026: installed 2.2.1 release candidate

A clean wheel from `87777fc2c24f97cd4fdbbf77734a3065491930ef` passed the
native gate on its first execution. Both hosts ran the installed `postbag mcp`
launcher. The package and runtime reported `2.2.1`. The core and adapter
loaded from the isolated venv, matched the reviewed source and wheel, and
remained unchanged throughout the run. Separate checks found identical
five-tool catalogs through `postbag mcp` and `postbag-mcp` with current and
legacy SDK clients. Each returned an empty private inventory.

The run used macOS 27.0.1, build 26A434, Python 3.14.6 and MCP SDK 2.2.0.
Codex CLI **0.159.0-alpha.12.1** reported model `gpt-6.1-sol`. Claude Code
**2.1.287** reported `claude-opus-5-5`. The unwrapped native `codex queue`
used default discovery in a private `CODEX_HOME`, without a `--remote`
override, and reached a disposable persisted thread. The user's personal
daemon and native Linux delivery were not tested.

| Check | Observed result |
|---|---|
| Ordinary delivery | The initial letter and reply were observed by both recipient sessions. |
| Final letter | After receipt and turn completion, 30.1091 seconds elapsed with no recipient send attempt or ledger change. Both hosts stayed alive. |
| Leave and refusal | The recipient left through MCP. The next send refused with `not_submitted` and the departure time, preserving the ledger bytes. |
| Deliberate rejoin | An explicit later harness instruction caused the recipient to join again. A later ordinary letter and reply were both received. |
| Accounting | Ten model-authored tool calls produced three joins, one leave and five submitted letters, with one additional send attempt refused. |
| Cleanup | Both clients and the private server exited 0, without forced shutdown. Native endpoints closed and the private authentication alias was removed. |

Receipt checks correlated tool arguments, outcomes, ledger records and
completed recipient turns. Claude's local stdout receipt markers were
harness instrumentation, not Postbag replies. The final observation is
evidence for this run, not a guarantee that every model obeys the footer.

The command sandbox reported read-only access, disabled network access and
`approvalPolicy: never`. Claude was launched with `--permission-mode manual`
and reported `permissionMode: default`. The preauthorized fixture tools
required no human prompt. `crossSessionInbound` was unset with empty Claude
setting sources. Native own-child classification was unobserved. No personal
configuration or installation changed during the gate. Claude used its
existing login and could write its usual caches or telemetry.

Candidate provenance:

```text
wheel          76cdd1df87c5980cff0218bb6eb54a1f82147c293cd01ee4c08f70aacee1f4d2
postbag.py     59a23112e1c6f88f9e39721f423b9d4950e519bbff15f9c0bbb004ae070fd6d2
postbag_mcp.py fe354cca37c92c6ce1e5ceaba71a37f0218542834124b1b31ee7528b7f4113c8
harness        81d2c29cf3f957f023933eca47f4e3146f53e1ce38a84401be255775431aaa2c
```

## 1 October 2026: installed 2.2.0 launcher candidate

A clean wheel from `c56d92d7ec2d4fb79a39b206db2bb0af8615d5be` passed the
native gate with both hosts configured to run the installed `postbag`
executable with `mcp` as its argument. The package, core and both console
entry points reported `2.2.0`. Runtime modules came from the candidate
venv's `site-packages`, matched the wheel and committed source, and remained
unchanged throughout the run.

The run used macOS 27.0.1, build 26A434, Python 3.14.6 and MCP SDK 2.2.0.
Codex CLI **0.159.2** reported model `gpt-6.1-sol`. Claude Code **2.1.287**
reported `claude-opus-5-5`. The unwrapped `codex queue` used default server
discovery in a private `CODEX_HOME`, with no `--remote` override. It reached
a disposable persisted thread. The user's personal running daemon and
native Linux delivery were not tested.

| Check | Observed result |
|---|---|
| Ordinary delivery | The initial letter and reply were observed in both recipient sessions. A later ordinary round trip after rejoining was also observed. |
| Final letter | Letter 3 requested a reply in its body but carried `final=true`. After recipient receipt and turn completion, 30.0992 seconds elapsed with no recipient send attempt or ledger change. Both hosts stayed alive. |
| Leave and refusal | The recipient left through its own MCP call at record 6. The next send returned `refused` and `not_submitted`, included the departure time and left the ledger byte-identical. No recipient receipt marker appeared. |
| Deliberate rejoin | An explicit later harness instruction caused the recipient to join again at record 7. Delivery then resumed. |
| Accounting | Ten model-authored calls produced three joins, one leave and five submitted letters. One additional send attempt was refused. Nine records and five letter ordinals were contiguous. Only letter 3 was final. |
| Cleanup | Both clients and the private server exited 0. No forced shutdown was needed. Native endpoints closed, the private authentication alias was removed and no extra correspondence appeared during shutdown. |

Receipt checks correlated exact tool arguments, structured outcomes, ledger
records and completed recipient turns. Claude's local receipt markers were
harness instrumentation, not Postbag replies. Submission receipts alone
were not taken as proof of receipt. The observation window describes this
run, not a guarantee that every model will obey a final footer. Leave did
not test recall of letters already queued.

The command sandbox reported read-only access, disabled network access and
`approvalPolicy: never`. Claude was launched with `--permission-mode manual`
and reported `permissionMode: default`. The preauthorized fixture tools
required no human prompt. `crossSessionInbound` was unset with empty Claude
setting sources. Native own-child classification was unobserved. No personal
configuration or installation changed. Claude used its existing login and
could write its usual caches or telemetry.

An earlier attempt was interrupted with the controlling chat turn after
two ordinary letters and one final letter. It produced no complete gate
verdict. Its private evidence was retained, its remaining private server
was stopped and its authentication alias removed. The successful attempt
used fresh sessions, a new challenge and the same candidate wheel and
harness. No letter was resent to the old peers.

Separate checks on the same installed wheel verified both console wrappers
with current and legacy SDK clients, identical five-tool catalogs and empty
private inventories. Five launcher tests passed outside the checkout.
The exact source passed **680 tests** with private HOME and
`ResourceWarning` as an error. All 21 root test files and the registry and
installation documents were present in the source archive. The wheel's
README metadata contained the registry ownership marker. Local uvx checks
also accepted both `postbag@2.2.0` and `postbag==2.2.0`, each with the matching
MCP extra. Those earlier uvx checks used a copied version-bumped fixture,
not this final candidate, and do not establish every registry client's
argument handling.

Candidate provenance:

```text
wheel          5412f561c00fe53d676eec2d8dc8d4efe86fdd69ad092d56193dc4cac0454110
sdist          fcb585c4bbff3504cfd9ab8b5f48c28bf05c4c7622bfbb5b0fe37144a32fdab4
postbag.py     772fe65e00df1d36116f76c5395ac5366638b318e70148bd88a41db3fd329a09
postbag_mcp.py fe354cca37c92c6ce1e5ceaba71a37f0218542834124b1b31ee7528b7f4113c8
harness        af2b577d77d7f8fd52423eaf64535ff78154e615931f72200048d7ff2b83f1c0
```

## 1 October 2026: installed 2.1.0.dev0 candidate

The clean wheel from `391fed550228b67d3d0a796418e2137865043f16` passed
the leave acceptance gate in fresh native sessions. Both runtime modules
came from the isolated installation's `site-packages`, matched the hashes
below and remained unchanged. The package, core and MCP entry point reported
`2.1.0.dev0`. Later commit `6489151` added tests without changing either
runtime module. This is candidate evidence, not a published 2.1 release.

The run used macOS 27.0.1, build 26A434, Python 3.14.6 and MCP SDK 2.2.0.
The app-server and queue executable reported **0.159.2**, with model
`gpt-6.1-sol`. **Claude Code 2.1.286** reported `claude-fable-5-1`.
The unwrapped `codex queue` used default discovery in a private
`CODEX_HOME`, without `--remote`. It reached a disposable persisted thread.
The user's personal desktop daemon was not tested.

| Check | Observed result |
|---|---|
| Initial exchange | Each model joined through MCP. The first letter and its reply were observed in their respective recipient sessions. |
| Final letter | Letter 3 had `final=true` and a body requesting a reply. After the recipient's receipt marker and turn completion, 30.1146 seconds elapsed with no recipient send attempt and no ledger change. Both hosts stayed alive. |
| Leave | An explicit harness instruction caused the recipient's own `postbag_leave` call. Its receipt named that peer, recorded line 6 and had `submission_state=null`. |
| Send after leave | The sender's next model-authored send returned `refused` and `not_submitted`, with the recorded departure time and `read/caller` recovery. The ledger remained byte-identical. No recipient receipt marker appeared. |
| Deliberate rejoin | A later harness instruction caused the recipient to join again, at record 7. A new ordinary letter and reply were then observed in both directions. |
| Accounting | Ten model-authored calls produced three joins, one leave and five submitted letters. The sixth send attempt was refused. The nine records had contiguous line numbers. Letter ordinals remained 1 through 5 across the leave and rejoin. Only letter 3 was final. |
| Cleanup | Both clients and the private server exited 0 without forced shutdown. Native endpoints closed, the private authentication alias was removed and no extra correspondence appeared during shutdown. |

Receipt evidence was correlated with the exact model tool arguments,
structured outcomes, ledger records and completed recipient turns.
The harness supplied leave and resumption instructions as user turns.
Claude's local stdout receipt markers were requested by the harness and
were not Postbag replies. Its native inbound text was not exposed.
Submission receipts and ledger entries alone were not treated as proof of
recipient receipt. The final observation covers this run and its stated
window. It does not isolate the footer from other model instructions or
prove that all conversations stop. Leave did not test recall of queued
letters, which remains unsupported.

The sender reported a read-only command sandbox, disabled network access
and `approvalPolicy: never`. Claude was launched with `--permission-mode manual`
and reported `permissionMode: default`, with no permission prompt. The harness left
`crossSessionInbound` unset and used empty Claude setting sources. Native
own-child classification was unobserved. The harness changed no personal
configuration or installation. Claude used its existing login and could
write its usual caches or telemetry.

The first native attempt completed the behavior checks but failed its final
verification because the harness compared the supported `@alpha` argument
literally with the ledger's normalized `alpha`. That failed report was
preserved. The harness was corrected to accept either documented spelling,
while still requiring exact bag, body, argument keys and Boolean flags.
Its offline checks and independent review rejected malformed alternatives.
The successful run used fresh sessions and the same wheel. No product code
changed between attempts.

Candidate provenance:

```text
wheel          d842e5419bb6d43b4da087f3f908eee015c01abb903217b55e722a4d9ef98ab0
sdist          b3421e7780c176bb034929a27a42fa154c400af67df265b975927e4d677a631d
postbag.py     85340f843b4b8298e568b0484cdf7ffa96dccb0c50e196c47e280750306dd456
postbag_mcp.py 1884192c471d8e5d0330a5f2ea8f481af032ddcdea63a8251df023ae10efc07f
harness        9a0e593632b8a08a90138898fa151094eefdf31a312c2e22a818962a6e1eb16f
```

Package and fixture checks:

- The frozen source at `6489151` passed **665 tests** on macOS with Python
  3.14.6, private HOME and `ResourceWarning` as an error.
- An installed wheel with the same runtime modules passed **181 MCP tests**
  outside the checkout. Rerunning the two subsequently changed files passed
  **38 tests**, covering **184 unique MCP cases** across the two runs.
- The candidate source archive passed all **52 core leave tests**. All 20
  root test files were included, matching the committed source. Wheel and
  source archive metadata checks passed.
- Offline Linux arm64 containers with Python 3.14.7, MCP 2.2.0 and a non-root
  user covered **184 unique MCP cases and 52 core leave cases**. Later runs
  covered changed files, with byte comparisons confirming unchanged files.
  Network access was disabled and fixtures used private homes. These runs
  tested no native vendor delivery on Linux.

Separate stdio checks used the actual published 2.0 modules and the candidate
modules in isolated fixtures. The 2.0 parent retained four tools while its
new worker reported `2.1.0.dev0` through inventory. A new parent using the
2.0 worker refused leave as `invalid_input`, with a null submission state,
unchanged ledger and a successful subsequent read. The 2.0 CLI and MCP
reader refused a ledger containing a leave. Its send refused before native
submission and its inventory marked the bag unavailable. All four cases
made zero native transport calls. These are version compatibility checks,
separate from the installed candidate's native exchange above.

An initial test run across a concurrently edited checkout encountered a
version change. The first frozen snapshot then found one outdated test
assertion that hardcoded `2.0.0`. Both results were retained and superseded
by the corrected frozen-source run above. CI results are not claimed here.
Native Linux delivery, a live Claude `/clear` transition and restricted
spawned-agent targets remain unverified. Forced process-tree termination can
still leave an unknown submission outcome.

## 1 October 2026: installed 2.0.0 candidate

The clean wheel from `8b87b4f59c990e5b550d62bde9d0a6c7c826cdff` passed the
2.0 native acceptance gate on its first run. Both runtime
modules came from the fresh venv's `site-packages`, matched the candidate
hashes below and remained unchanged throughout the run. The package and
MCP entry point reported `2.0.0`.

The run used macOS 27.0.1, build 26A434, Python 3.14.6 and MCP SDK 2.2.0.
The Codex app-server and native queue executable were
**0.158.0-alpha.2.1**, with model `gpt-6-astra`. **Claude Code 2.1.286**
reported model `claude-fable-5-1`. The unwrapped native queue used default
discovery in an isolated `CODEX_HOME`, with no `--remote` override. This
tested a private server and persisted disposable thread, not the user's
personal desktop daemon.

| Check | Observed result |
|---|---|
| Initial round trip | Codex sent letter 1 through MCP. Claude received it and sent letter 2, whose answer arrived in Codex. |
| Final letter | Codex sent letter 3 with `final=true`. Its body deliberately asked for a reply. After Claude's receipt marker and turn completion, a 30.0668-second observation recorded no Claude `postbag_send` attempt and no ledger change. Both hosts remained alive. |
| Later ordinary letter | A deliberate new instruction initiated ordinary letter 4. Claude received it and sent ordinary reply 5, which arrived in Codex. The earlier final letter did not close the bag. |
| Tools and ledger | Seven successful model-authored tools: two joins and five sends. All sends returned `submitted`. The ledger held two joins and five letters, with only letter 3 marked final and no `open` records. |
| Cleanup | Both clients and the private server exited 0 without forced shutdown. Native endpoints closed and the fixture authentication link was removed. |

Claude's local stdout receipt markers were harness instrumentation, not
Postbag correspondence replies. For the final letter, the native inbound
text was not exposed. Receipt evidence was the requested local marker
followed by recipient turn completion, and the observation window began
after both. The run observes final-letter guidance in this context. MCP
instructions and fixture setup were also in model context, so it does not
isolate the footer or establish universal loop prevention. Transport
receipts, ledger records and queue event counts alone were not treated as
proof of recipient receipt.

Codex reported a read-only command sandbox, network access disabled and
`approvalPolicy: never`. Claude was launched with manual permissions and
reported `permissionMode: default`. No Claude permission prompt occurred.
`crossSessionInbound` was unset by the harness, with empty Claude setting
sources. Native own-child classification was unobserved and is not inferred
from the independent processes. The harness changed no user configuration
or installation. Claude used its existing native login and could write its
usual local caches or telemetry.

Candidate provenance:

```text
wheel          9be6b61a9eba8968960f9d085794284e4a3e698dbbf0ec449aef66809cc497e9
postbag.py     226217c88c3d05f630806b55ddae0981b349363ef02fe0441566def6e456ab5b
postbag_mcp.py fc6a58f8a1d919827a05c9098d2272ce8539ba0a1ffa459e639cb4054e319171
```

For this exact candidate, the installed wheel passed **157 MCP tests**
outside the checkout. The extracted source archive passed **55 tests in
`test_core_2.py`**, including both descriptor-failure cases and the terminal
missing-bag recovery case. Both used pytest 9.1.1, private homes, scrubbed
session variables and `ResourceWarning` as an error. Wheel and source
archive metadata checks passed, and all 17 root test files were present in
the source archive with bytes matching the committed source.

A separate full-suite run on the same commit passed **586 tests** in
145 seconds, with private HOME and `ResourceWarning` as an error.
All **13 CI jobs** passed for `8b87b4f`, covering core and MCP tests on
macOS and Linux with Python 3.10, 3.12 and 3.14, plus package builds and
installed-distribution checks.
[Candidate CI](https://github.com/parasxos/postbag/actions/runs/36842969085).
The wheel hash above identifies the native-tested candidate. Release
documentation updates can change the distribution archive while leaving
these tested runtime module hashes unchanged.

Native Linux delivery, live Claude `/clear` and restricted spawned-agent
targets remain unverified. Forced process-tree termination can still leave
an unknown submission outcome. The 1.x results below retain their original
versions, test counts and limits.

## 1 October 2026: installed 1.4.0 release candidate

The clean wheel built from the release branch at `1bd4654` plus the version
bump passed the native release gate on macOS 27.0.1 with Python 3.14.6 and
MCP SDK 2.2.0, installed into a fresh virtual environment outside any
checkout. `postbag --version` and `postbag-mcp --version` both read `1.4.0`.

The decisive run was a cross-vendor CLI exchange between two live personal
sessions in bag `accept14`, opened by the human with a budget of 200. The
sender was **Claude Code 2.1.286** in bypass-permissions mode, running the
candidate CLI from its shell. The recipient was the desktop Codex
app-server, **codex-cli 0.158.0-alpha.2.1** (ChatGPT 26.924.22138, build
11645), reached through `/opt/homebrew/bin/codex` **0.157.1** as the queue
command, because the shell had no `POSTBAG_CODEX` and the former app-bundle
path no longer exists. This was the first live use of the filtered
subprocess environment: the queue command received none of the sender's
inbox, session or ledger variables.

| Check | Observed result |
|---|---|
| Claude to Codex | Candidate CLI `join claude` then `send codex` returned "delivered". The letter arrived in the existing Codex chat as an ordinary user-role turn and started a response. No approval was requested on the Codex side. |
| Codex to Claude | Codex replied through its installed 1.3.0 CLI, since its chat exposed no MCP tools. The reply arrived in the Claude session as a user turn with no approval prompt. |
| Exhaustion | The candidate CLI `send` in the spent bag `postbag-2046` returned "the exchange's letters are spent; stop and ask the human", exit 1, with the ledger byte-identical. |
| Ledger | Two letters in opposite directions in `accept14`, 198 remaining, both recorded under the names `claude` and `codex`. |

Native own-child classification was not observed. The sessions were the
user's personal running sessions, not isolated fixtures, and no recipient
policy was changed to make delivery pass. The MCP interface of the
candidate was exercised only by the automated wire suite in this run.
Both personal MCP servers still ran 1.3.0 during the exchange.

## 30 September 2026: installed 1.3.0 release candidate

The clean wheel built from `878a4a6` passed the native release gate on
macOS 27.0.1 (build 26A434), with Python 3.14.6 and MCP SDK 2.2.0. Both
modules were imported from the fresh environment's `site-packages`, outside
any checkout. The installed version and distribution metadata both read
`1.3.0`.

The decisive run used the current desktop Codex executable and app-server,
both **0.158.0-alpha.2.1**, and **Claude Code 2.1.285**. `POSTBAG_CODEX`
selected that real executable directly. The native queue used its standard
shared-server discovery in a private `CODEX_HOME`, with **no `--remote` and
no queue wrapper**. The private app-server listened on its normal control
socket. The personal desktop daemon and its live threads were untouched.
This closes the default-discovery gap in the earlier explicit-remote checks
below; it does not claim a test of the user's existing personal daemon.

| Check | Observed result |
|---|---|
| Codex to Claude | Model-authored MCP send returned `submitted`. Claude's idle native inbox started a turn and generated the nonce-derived answer. |
| Claude to Codex | Model-authored MCP reply returned `submitted`. Default native queue delivery started a third turn, which printed the exact nonce and computed answer. |
| Identity | MCP join recorded the concrete thread returned by the native host. Both peers joined once. |
| Ledger | Exactly two letters in opposite directions, with zero remaining. |
| Exhaustion | A separate human test prompt requested one extra model-authored send. It returned `refused` and `not_submitted`. The ledger stayed byte-identical and Claude received no further turn. |
| Cleanup | Both clients and the private server exited 0, endpoints closed, and the temporary authentication symlink was removed. |

Codex reported a read-only command sandbox with network access disabled,
`approvalPolicy: never`, and explicit approvals limited to the four Postbag
MCP tools. Claude launched with manual permissions and only those tools
allowlisted; its native initialization described the mode as `default`.
`crossSessionInbound` was unset, with empty setting sources. No interactive
human approval was needed during the exchange. Native own-child
classification was not observed, so independent processes are not presented
as proof that this classification was absent.

Additional runs exercised the same installed package with Codex 0.157.1 on
both queue and server, and with a 0.157.1 queue talking to the 0.158 desktop
server. Both exchanges and exhausted-budget refusals succeeded. The first
harness incorrectly expected a refused MCP call to have status `completed`
and treated all queue-change events as submissions. A separate version
probe also inherited a checkout working directory. These assertions were
corrected using the native error receipt, unchanged ledger, recipient turn
count, and an isolated installed-package probe; the original failed harness
report was retained. The mixed-version run exposed PATH selection and did
not meet its intended same-executable assertion. The final pinned desktop
run above passed without rewriting its initial verdict.

Candidate provenance:

```text
wheel         53e485058cd63e8454521a0bde9823ba87025d97a7e15a962a7f1c48b89f33e3
postbag.py    039237cfe4d86c2e28cd59297f8a2e06faff773d05d20dd44bee2e00840605dd
postbag_mcp.py fc624e16d897f5cff253691dd239cf049489d6fc4206fce29d206b5f501e237b
```

Later release-documentation edits change the distribution archive, not these
runtime modules. The stable candidate passed **397 tests**; its clean wheel
with the MCP extra passed **48 wire tests** outside the checkout. Wheel and
source archive metadata and fresh base installations passed. An actual
published 1.2.1 installation read a fixture ledger containing 1.3.0 MCP joins
and letters without modification, retaining the correct exhausted budget.
All 11 candidate CI jobs passed. Core jobs ran on macOS/Linux with Python
3.10, 3.12 and 3.14. MCP jobs ran on both systems with Python 3.10 and 3.14.
[Candidate CI](https://github.com/parasxos/postbag/actions/runs/36721883077).

Remaining limits: live Claude `/clear` was not exercised; native Linux
delivery and restricted spawned-agent targets remain unverified. Forced
termination of an entire process tree can still leave a submission outcome
unknown. The package does not infer receipt from a successful send alone.


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

## 30 September 2026: optional MCP interface

Development source `e7ca107` (`1.3.0.dev0`), Python 3.14.6 and MCP SDK 2.2.0.
These are development checks, not a package release or a global host upgrade.

### Caller identity

Two independent native Codex CLI 0.157.1 sessions each called the real
`postbag_join` tool once in a disposable named bag. Their thread IDs were
distinct. Each recorded door matched both that session's `thread.started`
event and the host's request `_meta.threadId`. The budget was unchanged.
The sessions retained the read-only sandbox, with temporary approval limited
to the fixture's join tool. This check established identity, not delivery.

Tagged source also confirms metadata injection in the active desktop runtime
0.158.0-alpha.2.1. Both hosts inject a concrete `threadId`; `sessionId` and
the shell's `CODEX_SESSION_ID` can instead identify a root and its descendants.
The CLI now prefers `CODEX_THREAD_ID`. Existing peers may need to rejoin.
Sources: [request metadata](https://github.com/openai/codex/blob/rust-v0.158.0-alpha.2.1/codex-rs/core/src/mcp_tool_call.rs#L521),
[shell identity](https://github.com/openai/codex/blob/rust-v0.157.1/codex-rs/core/src/unified_exec/process_manager.rs#L1443).

An isolated real Claude Code 2.1.285 MCP probe confirmed that its stdio child
receives the native socket and token. Per-call metadata included
`claudecode/toolUseId`, but no current conversation ID. Only presence flags
and metadata key names were returned; token values were not emitted.

These are vendor-specific identity mechanisms. MCP itself does not promise
either field set. Missing or conflicting identity refuses join and send.

### Claude lifecycle and `/clear`

Read-only inspection of installed Claude Code 2.1.285 found that `/clear`
changes the conversation UUID and retains ordinary MCP connections. The
inbox belongs to the host process; its socket uses the process ID, and its
token pair is generated when the inbox starts. The clear path does not
restart that inbox or regenerate those credentials. The MCP child's frozen
conversation ID can therefore become stale while its socket and token remain
usable. MCP joins deliberately omit that optional conversation ID.

This lifecycle conclusion is based on installed implementation inspection.
A live interactive `/clear` transition was not exercised. Nonstandard
environment allowlists, remote launchers and non-stdio MCP connections are
outside this check. The [documented inbox](https://code.claude.com/docs/en/cross-session-messaging#the-sessions-inbox-socket)
provides context, but is not a public guarantee that all MCP launch modes
inherit the same environment.

### Claude MCP round trip

Two independent persistent Claude Code 2.1.285 processes used normal manual
permissions, a strict temporary MCP configuration, and an allowlist of the
four Postbag tools. Built-in tools were disabled. The clients retained their
normal authentication; only each MCP child's `HOME` pointed to the shared
private fixture. No Python path override was used.

Each participant joined once through MCP. Alpha sent an arithmetic challenge
with a unique marker to beta. After beta's initial turn had finished, the
native inbox started another turn without a new harness prompt. Beta sent
the computed response through MCP. Alpha received that exact response in
another native turn. All four join/send outcomes were successful.

The final ledger held one open record, two joins and two letters in opposite
directions, with zero letters remaining. MCP joins contained no frozen
Claude conversation IDs. Both processes exited cleanly on stdin close and
removed their sockets. Logs were private. The native test exercised MCP
module SHA256 `c26a64f735192675750bad1a79d5c6adf809dd25663c4fe53eb91b228ff45616`;
subsequent changes added locale-independent JSON framing and clearer reply
instructions, covered by the final wire suite.

### Cross-vendor MCP round trip

The final modules at `e7ca107` passed a native exchange between Codex 0.157.1
and Claude Code 2.1.285. Both participants authored their own tool calls.
Codex used a read-only sandbox and Claude normal manual permissions. Only
the four Postbag MCP tools were approved. MCP executes in its server process
outside the command sandbox, so these explicitly approved tools could write
the fixture ledger and contact recipients despite the read-only shell policy.

Codex ran against a private native app-server, with an ordinary persisted
fixture thread and a retained client subscription. Its state directory,
SQLite database, logs and session history were private. An authentication
symlink let the native client use the existing account without copying or
printing credentials; the fixture removed that link at cleanup. Ephemeral
threads cannot receive queued messages, and idle threads can unload if their
owner disconnects, so neither is a suitable stand-in for this check.

The queue route was **private Unix WebSocket app-server via real
`codex queue --remote`**. A fixture wrapper inserted only `--remote` and
its private endpoint; it verified that every original Postbag argument was
preserved. It recorded native exit and queue acknowledgement without
logging the message argument. The production transport code was unchanged.

| Leg | Submission evidence | Receipt evidence |
|---|---|---|
| Codex to Claude | Native model `postbag_send` completed with `submitted`. | The idle Claude inbox started a new turn without another harness prompt and generated its own MCP reply. |
| Claude to Codex | Claude's `postbag_send` returned `submitted`; real queue exited 0 and returned a queued-message ID. | Queue events were observed. Codex started a third turn without another harness `turn/start` and printed the exact nonce and computed reply. |

The ledger gained exactly two letters in opposite directions and had zero
remaining budget. Neither agent called another tool after the final letter.
Both native runtimes and the app-server exited 0; endpoints closed. Final
module hashes matched before and after the run:

```text
postbag_mcp.py fc624e16d897f5cff253691dd239cf049489d6fc4206fce29d206b5f501e237b
postbag.py     5f052032ef1771c64b441cae47fb01542ecc8e2bba38f1a2398c6627e62212c6
```

This verifies native framing, queue acceptance, idle wakeup on a loaded
thread, host identity on actual MCP calls, and receipt in both directions.
**Default shared-server routing was not natively verified.** The shipped
transport normally omits `--remote` and relies on that default route, so
the private fixture does not establish current desktop/default-daemon
compatibility. Native Linux delivery also remains unverified.

### Mixed MCP and CLI round trip

A second cross-vendor fixture used the same final modules, versions and
private server route. Codex sent the challenge through its MCP tool. Claude
received it natively and replied through its Bash tool, using a fixture
wrapper that called the real `postbag.py` CLI. The wrapper fixed the private
ledger home, bag and recipient while preserving the caller's native identity.
Its Bash allowlist permitted only that wrapper. Claude's MCP send tool was
not approved for this run. This tests CLI interoperability, not whether a
model follows the envelope's printed shell reply command verbatim.

Native events showed exactly MCP join followed by Bash on the Claude side.
The CLI reported letter 2 of 2 with zero remaining. The real queue exited 0,
and a third Codex native turn received the exact nonce and computed reply.
The ledger contained two letters and the expected identities, with no extra
tool calls after the final letter. All processes exited 0, native endpoints
closed and the private authentication symlink was removed. This verifies
MCP/CLI interoperability over the same private route; it does not close the
default shared-server routing gap.

### Automated and independent verification

- Final local suite: **397 passed**. An independent Claude reviewer ran
  the full suite again in a fresh temporary home: **397 passed**.
- Real SDK wire tests: **48 passed**, including current and legacy protocol
  clients, both native transport fixtures, concurrency, malformed inputs,
  hostile working directories, ASCII locales, redaction and pagination.
- Raw stdin EOF during a fake send waited for submission and ledger recording
  at both one-second and 2.5-second native delays. This avoids conflating
  graceful server shutdown with an SDK client forcibly killing its children.
- Wheel and source archive built and passed metadata checks from a clean
  archived commit. Fresh base installations retained zero runtime dependencies
  and gave a clear missing-extra error for the MCP command. A fresh wheel
  installation with the extra passed all **48 wire tests** outside the source
  tree, where only the test file was copied.
- All **11 CI jobs** passed for `e7ca107`: core tests on macOS and Linux
  with Python 3.10, 3.12 and 3.14; MCP tests on both systems with Python
  3.10 and 3.14; and distribution build/install checks.
  [CI run](https://github.com/parasxos/postbag/actions/runs/36717026991).

The archived commit `79e23ff` and pushed `e7ca107` differ only in commit
messages. Both have tree `ab60edb5b1b20ef4ff9328f244d131303dcbd3cd`.
No wheel or source archive was published.
