The event log of a run, in order, with reason codes and cost, so any result can be traced.

## Use
- One row per event: time, state, what happened, then metadata in mono (tool, tokens, cost, reason code).
- Dots carry state with colour and also a text label in the heading ("Verified", "Flagged", "Stopped").
- Show model and adapter versions and the config hash in the audit view only, not on the main board.
- Rows are read-only. After export, the export and its approver appear as the last events.
- A failed run can be replayed from its recorded events.

## Tokens
`line`, `line-strong`, `ok`, `ok-soft`, `warn`, `warn-soft`, `danger`, `danger-soft`, mono type style.

## The consumer provides
The ordered event list from the run log.
