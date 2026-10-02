# vhs docs/demo.tape  (https://github.com/charmbracelet/vhs)
# Claude Code on the left, Codex on the right: scripted calls to two real
# postbag MCP servers, with stand-in native doors. See docs/demo_mcp.py.
Output docs/assets/demo.gif
Set Shell bash
Set FontSize 20
Set Width 1280
Set Height 730
Set Padding 24
Set LetterSpacing 0
Set Theme "Catppuccin Mocha"

Hide
Type "clear; ${PYTHON:-python3} docs/demo_mcp.py"
Enter
Sleep 1.5s
Show
Sleep 17s
