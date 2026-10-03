<!-- mcp-name: io.github.parasxos/postbag -->
<div align="center">

<img src="https://raw.githubusercontent.com/parasxos/postbag/v2.2.2/docs/assets/logo.png" width="96" height="96" alt="Postbag logo">

# postbag

**Let Codex and Claude Code talk to each other.**

A local MCP server. Ask Codex to review what Claude Code just wrote, or the
other way round. The answer arrives as a new turn. No copying text between
windows.

[![ci](https://github.com/parasxos/postbag/actions/workflows/ci.yml/badge.svg)](https://github.com/parasxos/postbag/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/postbag)](https://pypi.org/project/postbag/)
[![postbag MCP server](https://glama.ai/mcp/servers/parasxos/postbag/badges/score.svg)](https://glama.ai/mcp/servers/parasxos/postbag)
[![License](https://img.shields.io/badge/license-MIT-green)](https://github.com/parasxos/postbag/blob/v2.2.2/LICENSE)

</div>

![A real recorded run, edited and sped up. Codex joins bag review. Claude Code joins and asks Codex to review the last commit, and the request arrives in Codex as letter 1. Codex reads the diff, runs a test showing a failing job reported as None, and sends two findings back as a final letter. Claude Code checks them against the diff and agrees.](https://raw.githubusercontent.com/parasxos/postbag/main/docs/assets/demo-live.gif)

## Install

Needs Python 3.10 or later, Claude Code and a recent Codex CLI with
`codex queue`. Run both sessions on one machine with the same postbag version.
Delivery is tested on macOS.

```sh
pipx install 'postbag[mcp]'
claude mcp add --scope user postbag -- "$(command -v postbag-mcp)"
codex mcp add postbag -- "$(command -v postbag-mcp)"
```

Start a new session in each app, then run `/mcp`. postbag should list five
tools. For uvx and other setups, see
[MCP setup](https://github.com/parasxos/postbag/blob/v2.2.2/docs/mcp.md).

Or ask your agent: *Install postbag using
[llms-install.md](https://github.com/parasxos/postbag/blob/v2.2.2/llms-install.md).*

## Quick start

A bag is a named conversation. Both agents join the same one. Open Codex and
Claude Code in the same repository, so both see the same code.

1. In Codex:
   > Join postbag bag "review" as codex.
2. In Claude Code:
   > Join postbag bag "review" as claude, then ask codex to review my last commit.

Codex joins first so Claude Code has someone to write to. Approve the postbag
tools when asked. Codex gets the request as a new turn, and its reply lands in
Claude Code the same way. Either side can end with a final letter, which asks
for no reply.

## What to use it for

- **Cross review.** Claude Code finishes a change and asks Codex to review the diff before you commit.
- **Split work.** Codex writes the tests while Claude Code writes the implementation. They compare notes by letter.
- **Second opinion.** When one agent is stuck on a bug, it asks the other for a fresh read.

## Tools

Your agents call these. You just ask in plain words.

| Tool | What it does |
|---|---|
| `postbag_join` | Registers this session under a name in a bag, creating the bag if needed. |
| `postbag_send` | Sends a letter to a name in the bag. `final: true` asks for no reply. |
| `postbag_read` | Pages through the bag's history. |
| `postbag_bags` | Lists local bags with letter counts and registered names. |
| `postbag_leave` | Withdraws this session from the bag. History stays. |

## How it works

- **Native delivery.** Accepted letters become a new turn in the other session,
  through its own input. postbag adds no delivery daemon, polling or hooks.
- **No setup prompts.** Every letter ends with how to reply, or asks for no reply.
- **One shared history.** Each bag keeps a local log that either agent can page
  through with `postbag_read`.

A successful send confirms submission and recording. Neither the receipt nor
the log proves that the recipient accepted, read or acted on the letter.

## Security

- Each letter names its peer and asks the recipient to stay within the human's
  existing authorization. This is model guidance, not a security boundary.
  Connect only sessions you trust with the task.
- There is no letter limit. To confirm every MCP send, configure the host to ask
  before each `postbag_send` call.
- Ledgers under `~/.postbag/` hold Claude Code inbox tokens. New files use
  mode `0600`. Never commit or share them.

See [SECURITY.md](https://github.com/parasxos/postbag/blob/v2.2.2/.github/SECURITY.md).

[MCP setup](https://github.com/parasxos/postbag/blob/v2.2.2/docs/mcp.md) ·
[Concept](https://github.com/parasxos/postbag/blob/v2.2.2/CONCEPT.md) ·
[Changelog](https://github.com/parasxos/postbag/blob/v2.2.2/CHANGELOG.md) ·
[Contributing](https://github.com/parasxos/postbag/blob/v2.2.2/.github/CONTRIBUTING.md) ·
[MIT](https://github.com/parasxos/postbag/blob/v2.2.2/LICENSE)
