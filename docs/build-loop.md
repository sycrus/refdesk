# Build loop runbook

How to let Claude Code build refdesk in a loop without giving up control. This is the build loop (Claude Code building the project). It is separate from the product loop inside refdesk (PRD Section 10.2), but it follows the same principles: a verifier, stop conditions, a budget, checkpoints, and human gates.

## What it is

> The queue is GitHub Issues (see `docs/agents/issue-tracker.md`). Permissions for unattended runs are in `.claude/settings.json`.

- **Outer runner** (`scripts/run-loop.ps1`): asks `scripts/next_issue.py` for the first open `ready-for-agent` issue with no open blockers and no open PR (by milestone, then number), runs Claude Code on it, verifies the result, then commits to a fresh `build/loop-<date>-issue<N>` branch made from `origin/main`, pushes it, and opens a PR whose body ends in `closes #N`. It never merges and never pushes to `main`. `-Skip 2,6` skips issues by hand. Issues labelled `needs-info` are skipped until Joe removes the label. (Joe decided on 2026-10-31 that the loop follows the CLAUDE.md Git-hygiene rule — one branch and PR per issue — and that merging the PR closes the issue, so the queue clears itself.)
- **Staging rules** (`scripts/loop_git.py`, issue #182): the runner starts only on a clean tree, so everything changed afterwards is the agent's work. It stages those paths by name (never `git add -A`) and refuses any path under `data/` or `runs/`.
- **Live step view** (`scripts/loop_stream.py`, issue #185): the runner starts Claude Code through this script with `--output-format stream-json --verbose`. It prints one line per step as it happens, saves the full stream, records the session ID and enforces `-TimeoutMinutes`. Without it, `claude -p` prints only the final message and you see nothing until the run ends. The formatter is plain, tested Python. Unknown event types are shown, not dropped, and a malformed line never stops the stream.
- **Inner loop** (`/goal`): Claude Code's built-in completion-condition command. It keeps working across turns until a separate model judges the condition met. The condition must be provable from what Claude prints, and it must include a turn cap.
- **Deterministic verifier** (`scripts/verify.py`, also run in CI): frozen golden files (edits, deletions and renames), staged `.env`, secrets, and with `--run-tests` the same check steps as CI: `ruff check .`, pytest, and in `ui/` `npm run typecheck`, `npm test`, `npm run build` (issue #191). Every check runs even after one fails. A missing tool or `ui/node_modules` is a FAIL, not a skip. The browser tests (`npm run test:e2e`) stay CI-only. A test keeps the list in step with `ci.yml`. The agent's `/goal` prompt tells it to run the same command before it stops. A script, not a judgement.
- **Human gates**: issues labelled `ready-for-human`. The runner never picks them, and stops with exit code 3 when the remaining agent work is blocked by one.

## Prerequisites

- Claude Code v2.1.139 or later (`claude --version`). Check the current `/goal` documentation: https://code.claude.com/docs/en/goal
- Git, a Python environment with pytest, PowerShell 7 or WSL2.
- Node and npm, with `npm ci` run once in `ui/` (the verifier runs the UI checks).
- A clean working tree: no changes and no untracked files. The runner refuses otherwise (exit 5) and makes its own branch from `origin/main`.
- Read `CLAUDE.md` and `docs/prd.md` once yourself before running anything.

## Running it

1. **Dry run:** `./scripts/run-loop.ps1 -DryRun`. It prints the prompt for the next task and exits. Read it.
2. **One task:** `./scripts/run-loop.ps1 -MaxTasks 1`. Review the PR it opens and the log (`runs/build-loop.log`, `runs/loop-issue-<n>.txt`).
3. **A few tasks:** raise `-MaxTasks` only after one clean pilot. Keep `-TimeoutMinutes` and `-MaxTurns` small.
4. **Review before merging.** The runner never merges. Each task lands as its own PR from a `build/loop-<date>-issue<N>` branch. Read every diff on GitHub the way you would read a colleague's, then merge: `closes #N` in the PR body closes the issue on merge.
5. **Run again.** Merging clears the queue — closed issues and issues with open PRs are both skipped — so the next `-MaxTasks` picks fresh work.

## Watching a run and reviewing it afterwards

**Live.** The runner window prints one line per step, tagged with the issue:

```text
[#155] session 1f3c... started (claude-opus-5-5)
[#155] Read docs/prd.md
[#155] Edit src/refdesk/loop.py
[#155] Bash uv run pytest -q
[#155]   Bash ok
[#155]   Bash error: Exit code 1 ...
[#155] says: All acceptance criteria are met ...
[#155] done: success, 12 turns, session 1f3c...
```

A tool result names its tool and shows `ok` or `error` with the first part of the error. Exit codes are not in the stream, so a failing command shows as `error`. A line starting `?` is an event or block type the formatter does not know, or a line that was not JSON. It is shown on purpose. If you see many, check the stream format against the installed Claude Code version. A timeout ends with `[#155] killed: timeout after 30 min`.

**Afterwards.** Each run leaves these in `runs/` (gitignored):

| File | What it holds |
|---|---|
| `runs/loop-issue-<n>.jsonl` | The full stream, one JSON event per line: every tool call, its input and its result |
| `runs/loop-issue-<n>.txt` | The final message only, or `(no final result event)` if the run was killed or crashed |
| `runs/loop-issue-<n>.prompt.txt` | The exact `/goal` prompt the agent received |
| `runs/build-loop.log` | One CSV row per issue: `timestamp,issue,status,minutes,branch,session` |

To reopen a run interactively, take the session ID from the log (or from the `Session:` line the runner prints) and run `claude --resume <session-id>` in the repo. To scan a stream in PowerShell: `Get-Content runs/loop-issue-155.jsonl | uv run python scripts/loop_stream.py --replay --issue 155`. (A `build-loop.log` created before issue #185 has the old five-column header. Its new rows simply have a sixth field.)

## Stop conditions

| Stop | Mechanism |
|---|---|
| Task done | The `/goal` condition is met and the verifier passes |
| Turn cap | The turn clause in the condition (`-MaxTurns`) |
| Wall-clock | After `-TimeoutMinutes`, `loop_stream.py` kills the Claude Code process tree (`taskkill /T /F` on Windows) and exits 124. The runner logs `fail-timeout` and exits 1 without committing |
| Verifier fails | The runner stops on the first failure and leaves the tree for you to inspect |
| Human gate | Remaining agent work is blocked by a `ready-for-human` issue. The runner exits with code 3 |
| Judgement needed | The agent added `needs-info` to its issue. The runner logs `needs-info`, leaves the draft uncommitted and exits with code 4 |
| Dirty tree at start | Exit code 5, before anything runs |
| Staging refused | A changed path is under `data/` or `runs/`. Nothing is committed; exit code 1 |
| Push or PR failed | The commit exists on its branch (pushed if push succeeded). Log `fail-push` or `fail-pr`, exit code 1; open the PR by hand |
| Task count | `-MaxTasks` |
| Queue empty | Nothing unchecked |

If a task fails twice in a row, do not raise the cap. Stop and re-plan: split the task or fix its check.

## Writing good conditions

- Provable from printed output: "Run `pytest -q` and show it passing". Not "the code is clean".
- One task, one outcome. If a task needs two checks, state both.
- Include constraints the evaluator can see ("do not modify frozen golden-set files").
- Add the turn clause. The runner adds it for you.

## Guardrails

- **Learning-critical work is never automated.** Golden-set labels, ADR reasoning, decision-contract meanings, threat-model judgments and postmortem lessons are `ready-for-human` issues.
- **No paid API calls.** Default to the mock LLM server. Keys live in `.env`, which is gitignored.
- **Permissions.** Configure Claude Code's permission settings so the loop can run only what it needs (tests, git, the Python environment) and cannot reach the network or delete outside the repo. Do not use blanket permission-skipping options. Check the current settings documentation for the exact syntax before relying on an example.
- **Frozen files.** `verify.py` fails if a committed `evals/golden/golden-vN*.jsonl` is modified, deleted or renamed.
- **Costs.** A loop can use a lot of tokens quickly. Keep turn caps tight, and run `/goal` with no argument in an interactive session to see turns and tokens spent.

## Optional: a Stop hook

`/goal` is a wrapper around a session-scoped prompt-based Stop hook. For checks that must never depend on a model's judgement, you can also add your own Stop hook that runs `uv run python scripts/verify.py`. See the hooks documentation: https://code.claude.com/docs/en/hooks. Test it on a throwaway branch first.

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
