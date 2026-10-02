# vhs docs/demo.tape  (https://github.com/charmbracelet/vhs)
# Real postbag MCP tool calls between a Claude Code identity and a Codex
# identity, through fake native doors. See docs/demo_mcp.py.
Output docs/assets/demo.gif
Set Shell bash
Set FontSize 16
Set Width 1260
Set Height 800
Set Padding 20
Set Theme "Catppuccin Mocha"

Hide
Type "clear; ${PYTHON:-python3} docs/demo_mcp.py"
Enter
Show
Sleep 36s
