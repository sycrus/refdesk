The multistage approval gates as one stepper: six stages, automatic or human, with five states.

## Use
- Always show all gates, in order: Intake, Spend, Verify (automatic), Review, Approve, Export (human).
- Each gate has a state: passed, active, pending, blocked, skipped. Show the state in words under the label as well as in the node.
- A gate is never shown as passed until the action it requires has happened. Human gates show who must act.
- Blocked gates name the reason in the adjacent StopBanner.
- After Export the whole stepper is passed and the board is read-only.
- Selecting a gate scrolls to the surface that handles it (see the pattern table in the system README).

## Tokens
`accent`, `accent-soft`, `on-accent`, `line`, `line-strong`, `danger`, `danger-soft`, `radius-pill`, label and body-s type styles.

## The consumer provides
The state of each gate and a short status text. Roles and wording come from the run record.
