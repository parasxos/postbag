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
