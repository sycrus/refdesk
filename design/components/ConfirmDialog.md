The final approval step before the irreversible export. Summarises what will be exported and requires an explicit acknowledgement.

## Use
- Title states the action and count: "Approve and export 7 items".
- Show a summary by rights status and any items you marked as reviewed. Unverified items are excluded unless you reviewed them with a note.
- Require the acknowledgement checkbox (rights are as stated by the source; this is not legal advice) and the name field "Approving as". Both are recorded in the audit log.
- Say what happens next: the board becomes read-only and a receipt with the run ID is shown. Editing needs a new version.
- The primary button stays disabled until the acknowledgement is ticked, with the reason in text next to it.
- Focus is trapped inside and returned to the trigger on close. Escape cancels.

## Tokens
`card`, `line`, `shadow-pop`, `danger`, `danger-soft`, `accent`, `radius-lg`, display type style.

## The consumer provides
Counts by status, the list of reviewed items, the approver name and the run ID.
