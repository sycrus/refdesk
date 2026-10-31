# Issue tracker: GitHub

Work items for refdesk live as GitHub Issues on `sycrus/refdesk` (private). Use the `gh` CLI. Adapted from `sycrus/cultural-signal-graph`.

## Issue shape

```
## What to build
<one paragraph, with the PRD section it implements>

## Acceptance criteria
- [ ] <provable from printed output, e.g. "`uv run pytest -q` passes, including a test that ...">

## Blocked by
- #<n>
```

Each issue has one milestone (M0 to M5) and one triage label (see `triage-labels.md`).

## Conventions

- **Create**: `gh issue create --title "..." --milestone "M1 Ingest and baselines" --label needs-triage --body-file <file>`.
- **Read**: `gh issue view <n> --comments`.
- **List the agent queue**: `gh issue list --state open --label ready-for-agent --json number,title,milestone,body`.
- **Comment**: `gh issue comment <n> --body "..."`.
- **Labels**: `gh issue edit <n> --add-label "..." --remove-label "..."`.
- **Close**: `gh issue close <n> --comment "..."`, or `closes #<n>` in the commit or PR.

## Who moves what

- New issues start as `needs-triage`. **Only Joe** relabels an issue `ready-for-agent`.
- Claude Code works only on `ready-for-agent` issues with no open blockers, first by milestone, then by number.
- `ready-for-human` issues are learning-critical (golden labels, ADR reasoning, decision-contract meanings, threat-model judgements, postmortem lessons, interviews). Claude Code may draft scaffolding when asked, never the judgement.
- If an agent finds a judgement call mid-task, it comments on the issue, adds `needs-info`, and stops.

## Recording Joe's judgements

Joe gives a judgement in the issue thread. The thread is not versioned and is not next to the code, so the agent then copies the judgement into the repo file below, citing it as "(Joe, YYYY-MM-DD, #n)", and Joe checks the wording in the PR. Short answers are written up by the agent; reasoning (such as an ADR's `[Joe]` sections) is copied word for word, never paraphrased or extended. If the thread is ambiguous, the agent asks in the thread before writing anything.

| Kind of judgement | Where it is recorded |
|---|---|
| Architecture or process choice | The ADR: an amendment line plus Joe's reasoning (`docs/adr/`) |
| Q1 option meanings, error costs, abstention | `docs/decision-contract.md` |
| Loop values (caps, timeout, stuck rule, K) | `config/loop.yaml`, with the reason as a comment, and PRD 10.2 |
| Eval gates and thresholds | `docs/eval-gate-policy.md` |
| Golden labels and reviews | The labelling files under `evals/labelling/` |
| Postmortem hindsight | That postmortem in `postmortems/` |
| Threat-model attacker paths and residual risk | The threat-model doc |
| Anything else that changes the spec | `docs/prd.md` (on the ask list: Joe edits or approves) |

## Blocking

Use a `Blocked by` list in the body. An issue is unblocked when every listed issue is closed. (GitHub's native dependencies need `gh api`, which is on the ask list in `.claude/settings.json`.)

## Milestones and time-boxes

Milestone descriptions hold the day budget. When it runs out, cut scope and record the cut as a comment on the milestone's tracking issue. Do not extend the box.
