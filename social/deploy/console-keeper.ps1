# Runs as SYSTEM after an RDP disconnect: moves the disconnected administrator
# session back to the console so WeChat keeps rendering (no black screenshots).
$ErrorActionPreference = 'Stop'
$log = 'C:\xiaoqian\data\ops\console-keeper.log'
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
Start-Sleep -Seconds 3
# A disconnected session has no SESSIONNAME column, so the ID follows the user name directly.
$line = (quser.exe administrator 2>$null) | Where-Object { $_ -match '^\s*>?administrator\s+(\d+)\s' } | Select-Object -First 1
if (-not $line) {
    Add-Content $log ("{0} skip: no disconnected administrator session" -f (Get-Date -Format s))
    exit 0
}
$id = [int]([regex]::Match($line, '^\s*>?administrator\s+(\d+)\s').Groups[1].Value)
tscon.exe $id /dest:console
Add-Content $log ("{0} tscon session {1} -> console exit {2}" -f (Get-Date -Format s), $id, $LASTEXITCODE)
