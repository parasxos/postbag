# vhs docs/demo.tape  (https://github.com/charmbracelet/vhs)
Output docs/assets/demo.gif
Set Shell bash
Set FontSize 18
Set Width 1180
Set Height 600
Set Padding 18
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms

Hide
Type "source docs/demo-env.sh; clear"
Enter
Show

Type "# in the Claude Code session"  Enter
Type "in-claude postbag join claude" Sleep 300ms Enter Sleep 900ms
Type "# in the Codex session" Enter
Type "in-codex postbag join codex" Sleep 300ms Enter Sleep 900ms
Type "# in your own terminal: you set the budget" Enter
Type "postbag open --limit 4" Sleep 300ms Enter Sleep 1200ms
Type "# Claude writes, Codex wakes with the letter and answers" Enter
Type `in-claude postbag send codex "Review parser.py and send me the top three findings."` Sleep 300ms Enter Sleep 1400ms
Type `in-codex postbag send claude "Empty input returns None. Date errors are swallowed. No field bound."` Sleep 300ms Enter Sleep 1400ms
Type "postbag read" Sleep 300ms Enter
Sleep 4s
