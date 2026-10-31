# Build loop runner (PowerShell, Windows). One GitHub issue per iteration.
# Picks the first open ready-for-agent issue with no open blockers and no open PR
# (scripts/next_issue.py), runs Claude Code on it, verifies (scripts/verify.py), commits
# to a fresh build/loop-<date>-issue<N> branch made from origin/main, pushes it, and
# opens a PR ending in `closes #N`. Merging the PR closes the issue. The runner never
# merges and never pushes to main (one branch and PR per issue, CLAUDE.md; issue #187).
# It starts only on a clean tree and stages only the agent's changes, by name
# (scripts/loop_git.py, issue #182).
#
# Stops on: queue empty (0), agent work waiting on a ready-for-human issue (3), a failed
# check, staging refusal, push/PR failure or timeout (1), a picker error (2), the agent
# adding needs-info for Joe (4, work left uncommitted), a dirty tree at start (5), or
# -MaxTasks.
# Run with -DryRun first, then -MaxTasks 1, and review each PR before merging it.
param(
  [int]$MaxTasks = 3,
  [int]$TimeoutMinutes = 30,
  [int]$MaxTurns = 25,
  [int[]]$Skip = @(),
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force runs | Out-Null
$log = 'runs/build-loop.log'
if (-not (Test-Path $log)) { 'timestamp,issue,status,minutes,branch' | Out-File $log -Encoding utf8 }

# A clean start means everything changed after the agent runs is the agent's own work.
uv run python scripts/loop_git.py start
if ($LASTEXITCODE -ne 0) { Write-Host 'Refused: commit, stash or remove the changes above first.'; exit 5 }

# Built from a code point because PowerShell 5.1 reads .ps1 files as ANSI: a literal
# emoji in this file would be mangled on the way into the PR body.
$robot = [char]::ConvertFromUtf32(0x1F916)

$done = @()
$skipList = @($Skip)
while ($done.Count -lt $MaxTasks) {
  # PowerShell 5.1 drops empty-string arguments, so pass --skip only when there is something to skip.
  $pickArgs = @('run', 'python', 'scripts/next_issue.py')
  $skipNow = @($skipList + $done)
  if ($skipNow.Count -gt 0) { $pickArgs += @('--skip', ($skipNow -join ',')) }
  $picked = & uv @pickArgs
  $code = $LASTEXITCODE
  if ($code -eq 10) { Write-Host 'Queue empty.'; break }
  if ($code -eq 3) { Write-Host 'Needs you: the remaining agent work is blocked by a ready-for-human issue.'; exit 3 }
  if ($code -ne 0) { Write-Host "Picker failed (exit $code)."; exit 2 }
  $issue = $picked | ConvertFrom-Json
  $n = $issue.number

  # Only the issue number goes into the prompt: Claude reads the body with gh. This avoids
  # Windows PowerShell 5.1 mangling quotes from issue text when calling a native program.
  $prompt = "/goal Work on GitHub issue $n in sycrus/refdesk. Read it first with: gh issue view $n. Done when every acceptance criterion in that issue is met and you have printed the evidence for each one. Constraints: read CLAUDE.md and docs/prd.md first. Use the mock LLM server. Make no paid API calls. Do not modify frozen golden-set files. Do not commit, push or open a PR, the runner commits. Before you stop, run: uv run python scripts/verify.py --run-tests, and fix every FAIL it prints; the runner runs the same command and will not commit while it fails. If the task needs a judgement reserved for the user, comment on the issue, add the needs-info label, and stop. Stop after $MaxTurns turns."

  # One branch and PR per issue (CLAUDE.md), always from an up-to-date origin/main.
  # PR titles get the same quoting treatment as the prompt: double quotes in an issue
  # title are replaced, because PowerShell 5.1 mangles them on the way to a native program.
  git fetch -q origin
  if ($LASTEXITCODE -ne 0) { Write-Host 'git fetch failed.'; exit 2 }
  $branch = "build/loop-$(Get-Date -Format 'yyyyMMdd-HHmm')-issue$n"
  $prTitle = "build(#$n): " + ($issue.title -replace '"', "'")
  $prBody = "Closes #$n.`n`nBuilt by the build loop (docs/build-loop.md); verify.py --run-tests passed. Review against the issue's acceptance criteria before merging.`n`n$robot Generated with [Claude Code](https://claude.com/claude-code)"

  if ($DryRun) {
    Write-Host "DRY RUN: #$n $($issue.title)"
    Write-Host "DRY RUN: would create $branch from origin/main, then push it and open PR '$prTitle' with body:"
    Write-Host $prBody
    Write-Host $prompt
    exit 0
  }
  git switch -q -c $branch origin/main
  if ($LASTEXITCODE -ne 0) { exit 2 }

  $start = Get-Date
  $job = Start-Job -ScriptBlock { param($dir, $p) Set-Location $dir; & claude -p $p 2>&1 } -ArgumentList (Get-Location).Path, $prompt
  $finished = Wait-Job $job -Timeout ($TimeoutMinutes * 60)
  $out = Receive-Job $job
  if (-not $finished) { Stop-Job $job; $status = 'timeout' } else { $status = 'finished' }
  Remove-Job $job -Force
  $out | Out-File "runs/loop-issue-$n.txt" -Encoding utf8

  # The agent stopped for a judgement reserved for Joe: leave its draft for review.
  $labels = gh issue view $n -R sycrus/refdesk --json labels --jq '[.labels[].name] | join(",")'
  if ($labels -split ',' -contains 'needs-info') {
    $minutes = [math]::Round(((Get-Date) - $start).TotalMinutes, 1)
    "$(Get-Date -Format s),$n,needs-info,$minutes,$branch" | Out-File $log -Append -Encoding utf8
    Write-Host "Stopped at #${n}: the agent asked for your judgement (needs-info). Its draft is uncommitted on $branch."
    exit 4
  }

  uv run python scripts/loop_git.py stage
  if ($LASTEXITCODE -ne 0) {
    "$(Get-Date -Format s),$n,fail-staging,0,$branch" | Out-File $log -Append -Encoding utf8
    Write-Host "Stopped at #${n}: refused to stage (see above). Nothing was committed."
    exit 1
  }
  uv run python scripts/verify.py --run-tests
  $verified = ($LASTEXITCODE -eq 0)
  $minutes = [math]::Round(((Get-Date) - $start).TotalMinutes, 1)

  if ($status -eq 'finished' -and $verified) {
    $msgFile = New-TemporaryFile
    # WriteAllText writes UTF-8 without a BOM; Out-File on PowerShell 5.1 would add one.
    [IO.File]::WriteAllText($msgFile, "build(#$n): $($issue.title)`n`nrefs #$n`n`nCo-Authored-By: Claude Code <noreply@anthropic.com>`n")
    git commit -q -F $msgFile
    Remove-Item $msgFile

    git push -q -u origin $branch
    if ($LASTEXITCODE -ne 0) {
      "$(Get-Date -Format s),$n,fail-push,$minutes,$branch" | Out-File $log -Append -Encoding utf8
      Write-Host "Stopped at #${n}: committed on $branch but the push failed. Push and open the PR by hand."
      exit 1
    }
    $prBodyFile = New-TemporaryFile
    [IO.File]::WriteAllText($prBodyFile, $prBody)
    gh pr create --head $branch --title $prTitle --body-file $prBodyFile
    Remove-Item $prBodyFile
    if ($LASTEXITCODE -ne 0) {
      "$(Get-Date -Format s),$n,fail-pr,$minutes,$branch" | Out-File $log -Append -Encoding utf8
      Write-Host "Stopped at #${n}: pushed $branch but 'gh pr create' failed. Open the PR by hand."
      exit 1
    }
    "$(Get-Date -Format s),$n,pass,$minutes,$branch" | Out-File $log -Append -Encoding utf8
    $done += $n
  } else {
    "$(Get-Date -Format s),$n,fail-$status,$minutes,$branch" | Out-File $log -Append -Encoding utf8
    Write-Host "Stopped at #${n}: status=$status verified=$verified. Inspect runs/loop-issue-$n.txt and the working tree."
    exit 1
  }
}
if (-not $DryRun) { Write-Host "Done: $($done.Count) PR(s) opened ($($done -join ', ')). Review and merge each one; merging closes its issue." }
# Explicit: otherwise the script exits with the picker's last code (10 for an empty queue).
exit 0
