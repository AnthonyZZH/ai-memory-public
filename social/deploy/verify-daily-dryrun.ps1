$ErrorActionPreference='Stop'
$name='Xiaoqian-MediaLog-DryRun'
$before=(Get-ScheduledTaskInfo -TaskName $name).LastRunTime
Start-ScheduledTask -TaskName $name
$deadline=[DateTime]::UtcNow.AddSeconds(45)
do { Start-Sleep -Seconds 2; $task=Get-ScheduledTask -TaskName $name; $info=Get-ScheduledTaskInfo -TaskName $name } while (($task.State -eq 'Running' -or $info.LastRunTime -le $before) -and [DateTime]::UtcNow -lt $deadline)
if ($info.LastRunTime -le $before -or $task.State -eq 'Running') { throw 'task_verification_timeout' }
if ($info.LastTaskResult -ne 0) { throw "task_failed:$($info.LastTaskResult)" }
$latest=Get-ChildItem -LiteralPath 'C:\xiaoqian\logs\cleanup-reports' -Filter 'dry-run-*.txt' -File | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if ($null -eq $latest) { throw 'task_report_missing' }
Get-Content -LiteralPath $latest.FullName -Encoding UTF8
Write-Output 'scheduled_dry_run_executed_result_zero'
