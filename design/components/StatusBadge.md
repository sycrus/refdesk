Attribution and rights status with fixed wording, always an icon plus a label.

## Use
- Two separate badges per reference: attribution and rights. They fail differently, so never merge them.
- Wording is fixed (see the README table). Do not paraphrase.
- Colour is never the only signal: check for verified or open, alert for needs check or unverified, lock for permission required.
- A status the system inferred is never shown as verified.

## Tokens
`ok` / `ok-soft`, `warn` / `warn-soft`, `danger` / `danger-soft`, `radius-pill`, label type style.

## The consumer provides
The status value from the record's structured field. The component maps it to a label and an icon.
