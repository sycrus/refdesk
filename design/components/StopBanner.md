Says plainly why a run ended early and what the user can do next.

## Use
- The title always starts with "Stopped:" and names the reason: budget cap, step cap, timeout, no new items, source unavailable, or request declined.
- The body states the result in numbers ("9 of 12 items accepted") and what did not happen ("Nothing was exported").
- Offer the next actions as buttons: raise the cap (explicit), relax conditions, keep the partial board.
- Warning style for recoverable stops, danger style for blocks and declines. Both carry an icon and the full border, not a side stripe.
- Never hide or soften a stop reason.

## Tokens
`warn`, `warn-soft`, `danger`, `danger-soft`, `radius-lg`, body type styles.

## The consumer provides
The stop reason code, counts, and the available actions.
