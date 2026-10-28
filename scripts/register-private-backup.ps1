# Run after the owner has initialized and committed the private repository.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$taskName = 'AI-Memory-Private-Daily-Backup'
if (-not (Test-Path -LiteralPath 'E:\AI-Memory-private\.git' -PathType Container)) {
    throw 'Initialize and commit the private repository first.'
}
$existing = Get-ScheduledTask | Where-Object { $_.TaskName -eq $taskName }
if ($existing) {
    $backups = Join-Path $root 'backups'
    New-Item -ItemType Directory -Force -Path $backups | Out-Null
    $xmlPath = Join-Path $backups ("task-private-backup-before-" + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.xml')
    Export-ScheduledTask -TaskName $taskName -TaskPath $existing.TaskPath |
        Set-Content -LiteralPath $xmlPath -Encoding Unicode
    throw 'Existing task exported; stop for review rather than overwrite.'
}
$action = New-ScheduledTaskAction -Execute (Join-Path $root 'tools\basic-memory\Scripts\pythonw.exe') `
    -Argument ('"' + (Join-Path $root 'scripts\run_task.py') + '" backup-private') -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At '00:05'
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive -RunLevel Limited
# StartWhenAvailable is handled in phase 0.3.
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
Write-Output 'result_code=0'
