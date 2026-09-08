# README and landscape research

Checked 8 September 2026. These are selected primary-source reference designs,
not a ranking. README observations informed the shorter entry page; landscape
observations define scope without claiming unique capabilities.

| Source | Observation and lesson for Postbag |
|---|---|
| [OpenCode](https://github.com/anomalyco/opencode/blob/dev/README.md) | Shows its terminal interface near the top, followed by installation. Demonstrate the interaction before explaining the implementation. |
| [Goose](https://github.com/aaif-goose/goose/blob/main/README.md) | A short description and getting-started links lead into separate documentation. The README can be an entry point rather than a reference manual. |
| [Container Use](https://github.com/dagger/container-use) | A demo accompanies a concrete problem, installation and agent setup. Show one complete workflow. Its scope is agent development environments, rather than messaging. |
| [Agent Relay](https://github.com/AgentWorkforce/relay) | Provides channels, direct messages, threads, events and harness integrations. Agent messaging and wake-up already exist elsewhere; describe Postbag's smaller scope without exclusivity claims. |
| [MCP Agent Mail](https://github.com/Dicklesworthstone/mcp_agent_mail) | Provides identities, inboxes, searchable history and advisory file reservations through a FastMCP service with Git/SQLite storage. Postbag serves a fixed pair, without those team-coordination features. |
| [A2A](https://github.com/a2aproject/A2A) | Defines agent interoperability, discovery and task exchange across systems. Postbag is a native-session bridge and does not implement A2A. |
| [VHS](https://github.com/charmbracelet/vhs) | Produces terminal recordings from a reproducible tape. Keep the recording source, run actual CLI commands and identify simulated transports. |
| [apple-mail-mcp](https://github.com/parasxos/apple-mail-mcp) | Keeps its demo GIF in `docs/assets/demo.gif`. Reuse the in-repository asset pattern and descriptive caption. |

The selection includes tools introduced in 2025 and active in 2026:
[Goose's introduction](https://goose-docs.ai/blog/2025/01/28/introducing-codename-goose/)
is dated 28 January 2025; [Container Use's introduction](https://dagger.io/blog/agent-container-use/)
is dated 14 June 2025. OpenCode's [changelog](https://opencode.ai/changelog)
contains September 2026 releases. GitHub repository metadata records Agent Relay's
creation in December 2025 and MCP Agent Mail's in October 2025; both were active
in September 2026. Creation dates describe repositories, not necessarily product launches.

## Resulting direction

One clear description, a terminal GIF, installation, one role-labelled exchange,
one implementation paragraph, five security/limits bullets, and links to the
longer documents. No feature-comparison table or unsupported adoption claims.

Postbag's scope: one existing Claude Code session and one existing Codex session
on one machine, native delivery, one ledger, and a human-set letter budget.
The GIF demonstrates the CLI with temporary state and simulated transports; it
must not imply recorded live delivery or expose session credentials. Native
end-to-end compatibility remains a separate, explicitly qualified fact.

## Neighbours on one machine

Checked 8 September 2026 on each project's README. Star counts from the
GitHub API that day.

| Tool | Stars | What it is | How it differs from postbag |
|---|---|---|---|
| [hcom](https://github.com/aannoo/hcom) | 484 | One Rust binary; agents message, watch and spawn each other through vendor hooks and a local SQLite file. About eleven agents supported. | No daemon, like postbag, but N agents, delivery through hooks the tool installs rather than the vendor's own socket or queue, and collision detection instead of a budget. |
| [AgentBridge](https://github.com/raysonmeng/agent-bridge) | 331 | Claude Code and Codex as live peers over MCP, with a background daemon proxying the Codex app server over WebSocket. | Daemon and local ports required. Bounds the chat by message filtering and loop detection, not a human budget. |
| [Codex Bridge](https://github.com/abhishekgahlot2/codex-claude-bridge) | 56 | The two agents share a markdown chat file, delivered by a Claude Code channel plugin and a Codex stop hook. | Plugins on both sides and a research-preview flag. The agents end the conversation with a marker, so they bound it, not the human. |
| [MCP Agent Mail](https://github.com/Dicklesworthstone/mcp_agent_mail) | 2132 | Gmail-like inboxes, threads and advisory file leases over an MCP server with Git and SQLite behind it. | Server process, N agents, inbox polling instead of a wake-up, no budget. |
| [ClawTeam](https://github.com/HKUDS/ClawTeam) | 5530 | A leader agent spawns workers in git worktrees and coordinates through JSON inboxes or ZeroMQ. | Leader and workers, spawned by the tool, bounded by a task graph. |
| [Claude Squad](https://github.com/smtg-ai/claude-squad) | 8448 | A tmux TUI that runs several agents side by side in separate worktrees. | Isolation and switching only. The human relays. |

The vendor primitives postbag uses: Claude Code 2.1.224 (2026-08-07) added
cross-session messaging over a per-session socket, and Codex CLI 0.149
(2026-08-20) added `codex queue`. Nothing in the table combines a vendor
native wake-up on both sides, one append-only ledger as the only state, and
a budget the agents cannot extend. That is the whole of postbag's claim.
