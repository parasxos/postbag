# vhs docs/demo.tape  (https://github.com/charmbracelet/vhs)
Output docs/assets/demo.gif
Set Shell bash
Set FontSize 18
Set Width 1180
Set Height 700
Set Padding 18
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms

Hide
Type "source docs/demo-env.sh; clear"
Enter
Sleep 1.5s
Show

Type "# postbag demo: real commands against fake doors, no live session" Enter Sleep 800ms

Type "# in the first Claude Code session"  Enter
Type "in-ada postbag join claude ada" Sleep 300ms Enter Sleep 900ms
Type "# in the second Claude Code session" Enter
Type "in-bob postbag join claude bob" Sleep 300ms Enter Sleep 900ms
Type "# in your own terminal: you set the budget" Enter
Type "postbag open --limit 4" Sleep 300ms Enter Sleep 1200ms
Type "# ada writes, then bob answers" Enter
Type `in-ada postbag send @bob "Review parser.py, top three findings please."` Sleep 300ms Enter Sleep 1400ms
Type `in-bob postbag send @ada "Empty input, swallowed date errors, no field bound."` Sleep 300ms Enter Sleep 1400ms
Type "postbag read" Sleep 300ms Enter
Sleep 4s
