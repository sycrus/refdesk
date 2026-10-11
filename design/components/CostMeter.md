Spend against the cap, with a text value, so cost is never a surprise.

## Use
- Always show the number and the cap, not just a bar.
- Normal below 80% of the cap, warning from 80%, blocked at 100% with the stop reason shown in a StopBanner.
- The bar uses `role="progressbar"` and a label. State is also written in the note, not only coloured.
- Show the cap as the right end of the track. Raising the cap is an explicit action, never automatic.

## Tokens
`accent`, `warn`, `danger`, `sunken`, `radius-pill`, mono type style.

## The consumer provides
Spend, cap and a currency label.
