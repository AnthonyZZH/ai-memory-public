$ErrorActionPreference='Stop'
$name='Xiaoqian-MediaLog-DryRun'
if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { throw 'task_already_exists' }
$script='C:\xiaoqian\setup\daily-dryrun-report.ps1'
$action=New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$script`""
$trigger=New-ScheduledTaskTrigger -Daily -At '03:30'
$principal=New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Description 'Report only: no deletion, no --apply; media paths remain candidates.' | Out-Null
$task=Get-ScheduledTask -TaskName $name
if ($task.Actions.Arguments -match '--apply|-Apply' -or $task.Actions.Arguments -notmatch 'daily-dryrun-report\.ps1') { throw 'task_action_verification_failed' }
Write-Output 'daily_dry_run_task_registered_0330_system_no_apply'
