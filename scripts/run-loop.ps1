# Build loop runner (PowerShell, Windows). One GitHub issue per iteration.
# Picks the first open ready-for-agent issue with no open blockers (scripts/next_issue.py),
# runs Claude Code on it, verifies (scripts/verify.py), and commits to a build/loop-<date>
# branch. It never pushes or merges: open the PR yourself after reviewing the commits.
#
# Stops on: queue empty (0), agent work waiting on a ready-for-human issue (3), a failed
# check or timeout (1), a picker error (2), or -MaxTasks.
# Run with -DryRun first, then -MaxTasks 1, and review the diff before continuing.
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

$branch = "build/loop-$(Get-Date -Format 'yyyyMMdd-HHmm')"
if (-not $DryRun) { git switch -c $branch | Out-Null }

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
  $prompt = "/goal Work on GitHub issue $n in sycrus/refdesk. Read it first with: gh issue view $n. Done when every acceptance criterion in that issue is met and you have printed the evidence for each one. Constraints: read CLAUDE.md and docs/prd.md first. Use the mock LLM server. Make no paid API calls. Do not modify frozen golden-set files. Do not commit, push or open a PR, the runner commits. If the task needs a judgement reserved for the user, comment on the issue, add the needs-info label, and stop. Stop after $MaxTurns turns."

  if ($DryRun) { Write-Host "DRY RUN: #$n $($issue.title)"; Write-Host $prompt; exit 0 }

  $start = Get-Date
  $job = Start-Job -ScriptBlock { param($dir, $p) Set-Location $dir; & claude -p $p 2>&1 } -ArgumentList (Get-Location).Path, $prompt
  $finished = Wait-Job $job -Timeout ($TimeoutMinutes * 60)
  $out = Receive-Job $job
  if (-not $finished) { Stop-Job $job; $status = 'timeout' } else { $status = 'finished' }
  Remove-Job $job -Force
  $out | Out-File "runs/loop-issue-$n.txt" -Encoding utf8

  git add -A
  uv run python scripts/verify.py --run-tests
  $verified = ($LASTEXITCODE -eq 0)
  $minutes = [math]::Round(((Get-Date) - $start).TotalMinutes, 1)

  if ($status -eq 'finished' -and $verified) {
    $msgFile = New-TemporaryFile
    # WriteAllText writes UTF-8 without a BOM; Out-File on PowerShell 5.1 would add one.
    [IO.File]::WriteAllText($msgFile, "build(#$n): $($issue.title)`n`nrefs #$n`n")
    git commit -q -F $msgFile
    Remove-Item $msgFile
    "$(Get-Date -Format s),$n,pass,$minutes,$branch" | Out-File $log -Append -Encoding utf8
    $done += $n
  } else {
    "$(Get-Date -Format s),$n,fail-$status,$minutes,$branch" | Out-File $log -Append -Encoding utf8
    Write-Host "Stopped at #${n}: status=$status verified=$verified. Inspect runs/loop-issue-$n.txt and the working tree."
    exit 1
  }
}
if (-not $DryRun) { Write-Host "Done: $($done.Count) issue(s) on $branch. Review the commits, then push and open a PR." }
# Explicit: otherwise the script exits with the picker's last code (10 for an empty queue).
exit 0
