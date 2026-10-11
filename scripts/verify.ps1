# Deterministic checks for the build loop. Exit code 0 = pass.
# Run after `git add -A` so new files are included. Untested: review before relying on it.
$fail = 0

if (Test-Path tests) {
  pytest -q
  if ($LASTEXITCODE -ne 0) { Write-Host 'FAIL: tests'; $fail = 1 }
}

# Frozen golden-set files must not be modified (new versions are fine).
$modified = git diff --cached --name-status | Where-Object { $_ -match '^M\s+evals/golden/golden-v\d+\.jsonl' }
if ($modified) { Write-Host "FAIL: frozen golden file modified: $modified"; $fail = 1 }

# Possible secrets in added lines.
$added = git diff --cached -U0 | Where-Object { $_ -match '^\+' -and $_ -notmatch '^\+\+\+' }
$bad = $added | Where-Object { $_ -match '(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[''"][A-Za-z0-9_\-]{16,}[''"]' -or $_ -match 'sk-[A-Za-z0-9]{20,}' }
if ($bad) { Write-Host 'FAIL: possible secret in the diff'; $fail = 1 }

# A committed .env must never appear.
$env = git diff --cached --name-only | Where-Object { $_ -match '(^|/)\.env$' }
if ($env) { Write-Host 'FAIL: .env staged'; $fail = 1 }

if ($fail -eq 0) { Write-Host 'verify: PASS' }
exit $fail
