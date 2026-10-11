# Narrow wrapper for the Kev decision-model server in WSL2 (PowerShell, Windows).
#
# Why this exists: raw `wsl` commands are a full Linux shell, so they sit on the
# ask list in .claude/settings.json. This script exposes only a few fixed
# subcommands, so it can be allow-listed. Without it, every Kev start/stop would
# need a manual approval, or `wsl` would have to be allowed wholesale.
#
# train and merge are added with the M4 fine-tune issue. Untested until Kev is
# installed in ~/kev (see docs/prd.md Section 10.3).
param(
  [Parameter(Mandatory)][ValidateSet('status', 'vram', 'serve', 'stop')][string]$Cmd,
  [ValidatePattern('^[A-Za-z0-9_./@-]+$')][string]$Model = 'jaredpalmer/kev-4b@v1.0',
  [ValidateRange(1024, 65535)][int]$Port = 8009,
  [int]$MinFreeMiB = 9000
)
$ErrorActionPreference = 'Stop'
$Distro = 'Ubuntu-24.04'

function Get-FreeVramMiB {
  [int](nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | Select-Object -First 1)
}

switch ($Cmd) {
  'vram' {
    nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free --format=csv
  }
  'status' {
    # No nested double quotes: Windows PowerShell 5.1 mangles them when calling native programs.
    wsl -d $Distro -- bash -lc 'test -d ~/kev && git -C ~/kev describe --tags --always || echo kev-not-installed-in-~/kev'
    try { Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 3 } catch { Write-Host "No Kev server answering on port $Port" }
  }
  'serve' {
    $free = Get-FreeVramMiB
    if ($free -lt $MinFreeMiB) {
      Write-Host "Refusing to start: $free MiB VRAM free, need $MinFreeMiB. Stop other GPU jobs first (ollama stop <model>)."
      exit 4
    }
    wsl -d $Distro -- bash -lc "cd ~/kev && nohup uv run --extra serve python -m kev.serve --run '$Model' --port $Port > ~/kev/serve.log 2>&1 &"
    Write-Host "Started Kev ($Model) on port $Port. Log: ~/kev/serve.log in WSL."
  }
  'stop' {
    # [k] stops pkill matching its own command line, which also contains the pattern.
    wsl -d $Distro -- bash -lc 'pkill -f ''python -m [k]ev.serve'' && echo stopped || echo no-kev-server-running'
  }
}
