# Build loop runbook

How to let Claude Code build refdesk in a loop without giving up control. This is the build loop (Claude Code building the project). It is separate from the product loop inside refdesk (PRD Section 10.2), but it follows the same principles: a verifier, stop conditions, a budget, checkpoints, and human gates.

## What it is

> **2026-10-11:** the queue moved from `tasks/queue.md` to GitHub Issues (see `docs/agents/issue-tracker.md`). Until `run-loop.ps1` is rewritten to read issues, run tasks interactively: pick the first open `ready-for-agent` issue with no open blockers. Permissions for unattended runs are in `.claude/settings.json`.

- **Outer runner** (`scripts/run-loop.ps1`): takes the first `ready-for-agent` issue with no open blockers, runs Claude Code on it, verifies the result, commits, and moves on. *(Rewrite pending; it still reads `tasks/queue.md`.)*
- **Inner loop** (`/goal`): Claude Code's built-in completion-condition command. It keeps working across turns until a separate model judges the condition met. The condition must be provable from what Claude prints, and it must include a turn cap.
- **Deterministic verifier** (`scripts/verify.ps1`): tests, frozen golden files, secrets. A script, not a judgement.
- **Human gates**: tasks marked `[HUMAN]` stop the runner.

## Prerequisites

- Claude Code v2.1.139 or later (`claude --version`). Check the current `/goal` documentation: https://code.claude.com/docs/en/goal
- Git, a Python environment with pytest, PowerShell 7 or WSL2.
- A clean working tree on a branch you can throw away.
- Read `CLAUDE.md` and `docs/prd.md` once yourself before running anything.

## Running it

1. **Dry run:** `./scripts/run-loop.ps1 -DryRun`. It prints the prompt for the next task and exits. Read it.
2. **One task:** `./scripts/run-loop.ps1 -MaxTasks 1`. Review the commit and the log (`runs/build-loop.log`, `runs/loop-<ID>.txt`).
3. **A few tasks:** raise `-MaxTasks` only after one clean pilot. Keep `-TimeoutMinutes` and `-MaxTurns` small.
4. **Review before merging.** The runner never merges. It commits to a `build/loop-<date>` branch. Read every diff the way you would read a colleague's.

## Stop conditions

| Stop | Mechanism |
|---|---|
| Task done | The `/goal` condition is met and the verifier passes |
| Turn cap | The turn clause in the condition (`-MaxTurns`) |
| Wall-clock | `-TimeoutMinutes` kills the job |
| Verifier fails | The runner stops on the first failure and leaves the tree for you to inspect |
| Human gate | A `[HUMAN]` task. The runner exits with code 3 |
| Task count | `-MaxTasks` |
| Queue empty | Nothing unchecked |

If a task fails twice in a row, do not raise the cap. Stop and re-plan: split the task or fix its check.

## Writing good conditions

- Provable from printed output: "Run `pytest -q` and show it passing". Not "the code is clean".
- One task, one outcome. If a task needs two checks, state both.
- Include constraints the evaluator can see ("do not modify frozen golden-set files").
- Add the turn clause. The runner adds it for you.

## Guardrails

- **Learning-critical work is never automated.** Golden-set labels, ADR reasoning, decision-contract meanings, threat-model judgments and postmortem lessons are `[HUMAN]` tasks.
- **No paid API calls.** Default to the mock LLM server. Keys live in `.env`, which is gitignored.
- **Permissions.** Configure Claude Code's permission settings so the loop can run only what it needs (tests, git, the Python environment) and cannot reach the network or delete outside the repo. Do not use blanket permission-skipping options. Check the current settings documentation for the exact syntax before relying on an example.
- **Frozen files.** `verify.ps1` fails if a committed `evals/golden/golden-vN.jsonl` is modified.
- **Costs.** A loop can use a lot of tokens quickly. Keep turn caps tight, and run `/goal` with no argument in an interactive session to see turns and tokens spent.

## Optional: a Stop hook

`/goal` is a wrapper around a session-scoped prompt-based Stop hook. For checks that must never depend on a model's judgement, you can also add your own Stop hook that runs `scripts/verify.ps1`. See the hooks documentation: https://code.claude.com/docs/en/hooks. Test it on a throwaway branch first.

`/loop` re-runs a prompt on a time interval. Use it for watching things (a nightly eval, a failing CI run), not for building.

## What to review each time

- The commit diff, task by task.
- Whether tests assert behaviour or just exist.
- Any new dependency, config or network call.
- Whether anything touched a file the task did not mention.
- `docs/ai-assist-log.md`: log any defect the loop introduced and how you caught it.

## Known limits

- The scripts are untested on your machine. Treat the first runs as a pilot.
- The evaluator model checks only what Claude prints. A condition that is too easy will be met by a weak solution.
- Flags and settings change between Claude Code versions. Verify against the current documentation.
