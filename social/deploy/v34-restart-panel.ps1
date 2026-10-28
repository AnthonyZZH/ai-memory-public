$ErrorActionPreference='Stop'
$task='XiaoqianV34PanelStartOnce'
if (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue) { throw 'task_name_exists' }
$log='C:\xiaoqian\data\wechat\logs\events.jsonl'
$before=if(Test-Path -LiteralPath $log){@(Get-Content -LiteralPath $log -Encoding UTF8).Count}else{0}
$action=New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c C:\xiaoqian\app\Start-Xiaoqian-WeChat.cmd'
$principal=New-ScheduledTaskPrincipal -UserId 'administrator' -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $task -Action $action -Principal $principal | Out-Null
try { Start-ScheduledTask -TaskName $task; Start-Sleep -Seconds 15 }
finally { Unregister-ScheduledTask -TaskName $task -Confirm:$false }
$panels=@(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -match '(?i)(?:^|[\\/\s"''])app\.py(?:[\s"'']|$)' -and $_.SessionId -eq 2 })
if ($panels.Count -ne 2) { throw 'panel_start_unconfirmed' }
$lines=if(Test-Path -LiteralPath $log){@(Get-Content -LiteralPath $log -Encoding UTF8)}else{@()}
if ($lines.Count -lt $before) { throw 'events_log_truncated' }
$errors=0
foreach ($line in @($lines | Select-Object -Skip $before)) {
    if (!$line.Trim()) { continue }
    $row=$line | ConvertFrom-Json
    if ($row.event -eq 'error') { $errors++ }
}
Write-Output ('panel_session2_processes={0};new_events={1};new_error_events={2}' -f $panels.Count,($lines.Count-$before),$errors)
if ($errors -gt 0) { throw 'new_error_event' }
