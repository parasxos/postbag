# Fake doors for the README demo. Source this in a shell, then run postbag.
# Nothing here touches a real session: the ledger is temporary, the Claude
# door is a throwaway socket, the Codex door is a script that exits 0.
unset CLAUDE_CODE_MESSAGING_SOCKET CLAUDE_CODE_MESSAGING_TOKEN CODEX_SESSION_ID
PS1='$ '
PATH="$PWD:$PATH"   # run the checkout being documented
DEMO=$(mktemp -d)
trap 'kill $LISTENER 2>/dev/null; rm -rf "$DEMO"' EXIT
export POSTBAG_LEDGER="$DEMO/ledger.jsonl"
export POSTBAG_CODEX="$DEMO/codex"
printf '#!/bin/sh\nexit 0\n' > "$POSTBAG_CODEX" && chmod +x "$POSTBAG_CODEX"
python3 - "$DEMO/claude.sock" <<'PY' &
import socket, sys
s = socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); s.listen()
while True:
    c, _ = s.accept(); c.recv(65536); c.close()
PY
LISTENER=$!
sleep 0.3
in-claude() { CLAUDE_CODE_MESSAGING_SOCKET="$DEMO/claude.sock" CLAUDE_CODE_MESSAGING_TOKEN=demo "$@"; }
in-codex()  { CODEX_SESSION_ID=thread-7 "$@"; }
