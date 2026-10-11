Primary, secondary, ghost and danger actions, 40px high, with a visible focus ring.

## Use
- One primary action per view. In the approval flow it is the single forward action ("Approve and export").
- Secondary is the default. Ghost is for low-emphasis actions such as "More like this".
- Danger is for irreversible or blocking actions. It is always labelled in words ("Export and lock board").
- Disabled buttons explain why in adjacent text. Never leave a disabled primary without a reason.

## Tokens
`accent`, `accent-hover`, `on-accent`, `line-strong`, `danger`, `danger-soft`, `radius-md`, `focus`.

## The consumer provides
The label, the handler, and the reason text for any disabled state.
