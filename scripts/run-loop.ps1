# Build loop runner. One task per iteration. Stops at [HUMAN] tasks, on a failed check, on timeout.
# Untested. Run with -DryRun first, then -MaxTasks 1, and review the diff before continuing.
param(
  [int]$MaxTasks = 3,
  [int]$TimeoutMinutes = 30,
  [int]$MaxTurns = 25,
  [string]$Queue = 'tasks/queue.md',
  [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force runs | Out-Null
$log = 'runs/build-loop.log'
if (-not (Test-Path $log)) { 'timestamp,task,status,minutes,branch' | Out-File $log -Encoding utf8 }

$branch = "build/loop-$(Get-Date -Format 'yyyyMMdd-HHmm')"
if (-not $DryRun) { git checkout -b $branch | Out-Null }

$done = 0
while ($done -lt $MaxTasks) {
  $lines = Get-Content $Queue
  $idx = -1
  for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -match '^- \[ \] ') { $idx = $i; break } }
  if ($idx -lt 0) { Write-Host 'Queue empty.'; break }

  if ($lines[$idx] -match '^- \[ \] (\S+)( \[HUMAN\])? \| (.+?) \|\| (.+)$') {
    $id = $Matches[1]; $human = $Matches[2]; $desc = $Matches[3]; $check = $Matches[4]
  } else {
    Write-Host "Cannot parse queue line: $($lines[$idx])"; exit 2
  }

  if ($human) { Write-Host "Needs you: $id $desc"; exit 3 }

  $prompt = "/goal Task ${id}: $desc Done when: $check Constraints: read CLAUDE.md and docs/prd.md first. Use the mock LLM server. Make no paid API calls. Do not modify frozen golden-set files. If the task needs a judgement reserved for the user, stop and report. Stop after $MaxTurns turns."

  if ($DryRun) { Write-Host "DRY RUN: $id"; Write-Host $prompt; break }

  $start = Get-Date
  $job = Start-Job -ScriptBlock { param($dir, $p) Set-Location $dir; & claude -p $p 2>&1 } -ArgumentList (Get-Location).Path, $prompt
  $finished = Wait-Job $job -Timeout ($TimeoutMinutes * 60)
  $out = Receive-Job $job
  if (-not $finished) { Stop-Job $job; $status = 'timeout' } else { $status = 'finished' }
  Remove-Job $job -Force
  $out | Out-File "runs/loop-$id.txt" -Encoding utf8

  git add -A
  & "$PSScriptRoot/verify.ps1"
  $verified = ($LASTEXITCODE -eq 0)
  $minutes = [math]::Round(((Get-Date) - $start).TotalMinutes, 1)

  if ($status -eq 'finished' -and $verified) {
    $lines[$idx] = $lines[$idx] -replace '^- \[ \]', '- [x]'
    $lines | Set-Content $Queue
    git add -A
    git commit -m "build($id): $desc" | Out-Null
    "$(Get-Date -Format s),$id,pass,$minutes,$branch" | Out-File $log -Append -Encoding utf8
    $done++
  } else {
    "$(Get-Date -Format s),$id,fail-$status,$minutes,$branch" | Out-File $log -Append -Encoding utf8
    Write-Host "Stopped at ${id}: status=$status verified=$verified. Inspect runs/loop-$id.txt and the working tree."
    exit 1
  }
}
Write-Host "Done: $done task(s) on $branch."
