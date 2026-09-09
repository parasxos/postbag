# Fake doors for the README demo. Source this in a disposable shell, as vhs
# provides, then run postbag. It replaces HOME and unsets the session
# variables, so do not source it in an interactive shell you keep using.
# Nothing here touches a real session or your own bags: HOME is a temporary
# directory, so the default bag lives there, and each Claude door is a
# throwaway socket that accepts a connection and drops it.
unset CLAUDE_CODE_MESSAGING_SOCKET CLAUDE_CODE_MESSAGING_TOKEN CODEX_SESSION_ID POSTBAG_LEDGER
PS1='$ '
PATH="$PWD:$PATH"   # run the checkout being documented
DEMO=$(mktemp -d)
trap 'kill $LISTENERS 2>/dev/null; rm -rf "$DEMO"' EXIT
export HOME="$DEMO"
LISTENERS=
for door in ada bob; do
python3 - "$DEMO/$door.sock" <<'PY' &
import socket, sys
s = socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); s.listen()
while True:
    c, _ = s.accept(); c.recv(65536); c.close()
PY
LISTENERS="$LISTENERS $!"
done
sleep 0.3
in-ada() { CLAUDE_CODE_MESSAGING_SOCKET="$DEMO/ada.sock" CLAUDE_CODE_MESSAGING_TOKEN=demo-ada "$@"; }
in-bob() { CLAUDE_CODE_MESSAGING_SOCKET="$DEMO/bob.sock" CLAUDE_CODE_MESSAGING_TOKEN=demo-bob "$@"; }
