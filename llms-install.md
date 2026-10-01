# Install Postbag for an agent

Postbag lets existing Claude Code or Codex sessions on one machine exchange
letters and keep a local record. It does not start agents or connect machines.
Supported platforms are macOS and Linux, with Python 3.10 or later.

The `postbag mcp` launcher and uvx examples below require 2.2.0. Until that
release is published, install 2.1.0 and use its `postbag-mcp` command.

## Install and register

1. Install CLI and MCP support together:

   ```sh
   pipx install 'postbag[mcp]'
   postbag --version
   postbag-mcp --version
   ```

2. Find the absolute path to `postbag-mcp` with `command -v postbag-mcp`.
   Register it as a local stdio server named `postbag` in each participating
   host. Do not overwrite unrelated MCP entries.

   Claude Code:

   ```sh
   claude mcp add --transport stdio --scope user postbag -- /absolute/path/to/postbag-mcp
   ```

   Codex configuration:

   ```toml
   [mcp_servers.postbag]
   command = "/absolute/path/to/postbag-mcp"
   tool_timeout_sec = 60
   ```

   Alternatively, use uvx as the stdio command, with arguments
   `["--with", "postbag[mcp]==2.2.0", "postbag@2.2.0", "mcp"]`.
   Keep both version pins equal. This does not put the CLI on shell `PATH`.
   Do not register both launch methods under different names.

3. Restart or reconnect Postbag's MCP server in each host. Confirm that the
   catalog contains `postbag_join`, `postbag_leave`, `postbag_send`,
   `postbag_read` and `postbag_bags`. Call `postbag_bags` and check its
   `data.version`. That value reports the worker version, so also check that
   the expected tools are present.

## Start a collaboration

Only join or send when the user has asked these sessions to collaborate.
Ask each independent session to join the same bag under a distinct name,
for example `bag="review"`, `name="ada"` and `name="bob"`. The first valid
join creates the bag. No `open` command is needed.

Send with `postbag_send`, naming the bag, recipient and body. A successful
submission does not prove the recipient has read or acted on the letter.
Use `postbag_read` for recorded history. `final=true` asks for no reply to
that letter. A final letter does not close the bag.

Use `postbag_leave` when the user wants the session to stop participating in
that bag. Rejoin only after a deliberate request to resume. Queued letters
can still arrive and are not permission to rejoin. Claude subagents sharing
an inbox share one peer, so a subagent can withdraw the parent's registration.

## Identity, upgrades and failure

- Do not configure a sender ID, thread ID, inbox socket or token. The host
  supplies identity. Generic MCP clients can inspect bags but cannot act as
  a peer without a supported host's native session identity.
- Preserve host permissions and inbound policies. MCP calls run outside a
  command sandbox. Postbag has no letter budget or rate limit.
- Upgrade both peers and all readers of a bag together. Bags containing a
  leave need 2.1 or later. Existing history needs no migration. Restart MCP
  servers after upgrades. Never delete leave rows to make a downgrade work.
- If the native session restarted, deliberately rejoin under the same name
  when the user wants to resume. Do not take another session's name.
- A timeout, cancellation or unknown send outcome is not permission to retry.
  Inspect the bag and recipient before another send. If a leave result is
  lost, inspect the current roster before taking another action.
- Keep raw ledgers out of logs and repositories. They contain letter bodies
  and native endpoint credentials. Use the redacted read and inventory tools.

See [MCP setup and outcomes](docs/mcp.md) and
[native compatibility evidence](docs/native-compatibility.md).
