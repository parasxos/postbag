<!-- mcp-name: io.github.parasxos/postbag -->
<div align="center">

<img src="https://raw.githubusercontent.com/parasxos/postbag/v2.2.1/docs/assets/logo.png" width="96" height="96" alt="Postbag logo">

# postbag

**Two agents, one bag of letters.**

Your Claude Code and Codex sessions write to each other. Ask one to review
the other's diff, split a task, or get a second opinion, without copying
text between windows.

[![ci](https://github.com/parasxos/postbag/actions/workflows/ci.yml/badge.svg)](https://github.com/parasxos/postbag/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/postbag)](https://pypi.org/project/postbag/)
[![postbag MCP server](https://glama.ai/mcp/servers/parasxos/postbag/badges/score.svg)](https://glama.ai/mcp/servers/parasxos/postbag)
[![License](https://img.shields.io/badge/license-MIT-green)](https://github.com/parasxos/postbag/blob/v2.2.1/LICENSE)

</div>

![Scripted demo: a Codex identity and a Claude Code identity call two postbag MCP servers to join a bag, exchange a review, mark the last letter final, leave and read the bag](https://raw.githubusercontent.com/parasxos/postbag/v2.2.1/docs/assets/demo.gif)

<sub>Scripted calls to two real postbag MCP servers, with fake native doors.
[Demo source](https://github.com/parasxos/postbag/blob/v2.2.1/docs/demo_mcp.py).</sub>

## What it does

- **Native delivery.** A letter arrives in the recipient as a new user turn,
  through its own input: Claude Code's inbox or `codex queue`. postbag adds
  no delivery daemon, polling or hooks.
- **One shared record.** Every join, letter and leave goes into one
  append-only ledger per bag, which both agents and you can read.
- **Set up by the agents.** Joining a bag creates it. Nothing to run in a
  separate terminal.
- **The session is the sender.** Identity comes from the host, never from
  tool arguments.

## Install

```sh
pipx install 'postbag[mcp]'
```

Python 3.10 or later, on macOS or Linux. Then register the server once in
each host.

**Claude Code**

```sh
claude mcp add --transport stdio --scope user postbag -- "$(command -v postbag-mcp)"
```

**Codex**, in `~/.codex/config.toml`, with the path that `command -v postbag-mcp` prints:

```toml
[mcp_servers.postbag]
command = "/Users/you/.local/bin/postbag-mcp"
tool_timeout_sec = 60
```

Reconnect or restart each host's MCP server, then check that the five
postbag tools are listed, for example with `/mcp` in Claude Code.
Codex delivery uses the `codex` binary's `queue` command, 0.149 or later.
Set `POSTBAG_CODEX` if it is neither on `PATH` nor in the ChatGPT app.
To run without installing, as listed in the official MCP registry:
`uvx --with 'postbag[mcp]==2.2.1' postbag@2.2.1 mcp`.
Agents can follow [llms-install.md](https://github.com/parasxos/postbag/blob/v2.2.1/llms-install.md).

## Use it

Open a Codex session and a Claude Code session in the same repository.

1. In Codex: *"Join the postbag bag review as bob and wait for letters."*
2. In Claude Code: *"Join bag review as ada and ask bob to review my last commit."*

Each letter ends with how to reply, so neither agent needs instructions.
Watch the conversation with `postbag --bag review read`. When the work is
done, ada can send a final letter, which asks for no reply, and either side
can leave the bag.

## The five tools

| Tool | What it does |
|---|---|
| `postbag_join` | Registers this session under a name in a bag, creating the bag if needed. |
| `postbag_send` | Sends a letter to a name in the bag. `final: true` asks for no reply. |
| `postbag_read` | Pages through the bag's history. |
| `postbag_bags` | Lists local bags with their letter counts and registered names. |
| `postbag_leave` | Withdraws this session from the bag. History stays. |

The CLI has the same verbs: `postbag join`, `send`, `read`, `bags` and `leave`.

## Good to know

- **No brake.** postbag sets no letter limit. Your hosts' tool approvals and
  the agents' judgement decide how long a conversation runs.
- **A letter is a user turn.** Connect only sessions you trust with the
  task. The ledger holds each Claude session's inbox token. It is created
  with mode `0600`, so keep it out of git and logs.
- **Same machine, same version.** Two sessions are the supported use. After
  an upgrade, upgrade both and reconnect both MCP servers.
- **Restarted session.** If a session comes back with a new identity and
  should keep corresponding, ask it to join the bag again under the same name.
- **Submitted, not read.** A send returns once the recipient's door took the
  letter, not when the agent read it.

[Concept](https://github.com/parasxos/postbag/blob/v2.2.1/CONCEPT.md) ·
[MCP setup and limits](https://github.com/parasxos/postbag/blob/v2.2.1/docs/mcp.md) ·
[Security](https://github.com/parasxos/postbag/blob/v2.2.1/.github/SECURITY.md) ·
[Changelog](https://github.com/parasxos/postbag/blob/v2.2.1/CHANGELOG.md) ·
[Contributing](https://github.com/parasxos/postbag/blob/v2.2.1/.github/CONTRIBUTING.md) ·
[Tools that do more](https://github.com/parasxos/postbag/blob/v2.2.1/docs/readme-research.md) ·
[MIT](https://github.com/parasxos/postbag/blob/v2.2.1/LICENSE)
