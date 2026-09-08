# bridge: two agents correspond by letters

## The idea

Two agents on one machine talk the way two people in adjacent offices do.
One writes a letter and slides it under the other's door. The door is
whatever wakes that agent natively. Every letter is kept in one ledger.
Nothing else exists.

## Five nouns

| Noun | Definition |
|---|---|
| **peer** | One of exactly two agents: `claude` or `codex`. |
| **door** | The native way to reach a peer. Claude: its inbox socket and token. Codex: its thread id, reached with `codex queue`. |
| **letter** | Text from one peer to the other. Numbered, timestamped, delivered, then recorded. |
| **exchange** | A budget of letters, opened by a human. |
| **ledger** | One append-only file. The whole history, the only state. |

## Four verbs

| Verb | Who | Effect |
|---|---|---|
| `join` | a peer, from inside its own session | records its door |
| `open` | a human, outside both sessions | starts an exchange with a budget of letters |
| `send` | a peer | knocks on the recipient's door, then records the letter |
| `read` | anyone | prints the ledger |

## Principles

1. **Two peers, so addressing one names the other.** `send codex` is
   from claude. There is no `--from`.
2. **The door is native.** No daemon, no polling, no hooks. Delivery
   uses the mechanism each vendor built to reach its own agent.
3. **The letter teaches its reader how to answer.** Each delivered
   letter begins with its number, its sender, and the one command that
   replies. Neither agent needs prior instruction.
4. **The ledger is the truth.** A letter exists iff it was delivered and
   then recorded. Doors and budgets are read from the ledger, never from
   anywhere else. History is a file you can `cat`.
5. **The human bounds the conversation.** An exchange holds the letters
   its opener granted. When they are spent, `send` refuses and tells the
   agent to stop. `open` refuses inside either session, by the same
   signal `join` trusts, so agents cannot extend their own budget.
6. **Everything the agents share is the repository.** The bridge moves
   text, never files. Work products travel through git.

## What is deliberately absent

Roles, topics, threads, acknowledgements, retries, a server, a
configuration file, a protocol document for the agents. Each was
considered and found to add a noun without adding a capability.
