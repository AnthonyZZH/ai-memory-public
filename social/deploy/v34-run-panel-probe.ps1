$ErrorActionPreference='Stop'
$task='XiaoqianV34PanelProbeOnce'; $output='C:\xiaoqian\setup\v34-panel-status.json'
if ((Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue) -or (Test-Path -LiteralPath $output)) { throw 'probe_state_exists' }
$action=New-ScheduledTaskAction -Execute 'C:\xiaoqian\app\wechat\.venv\Scripts\pythonw.exe' -Argument '-B -X utf8 C:\xiaoqian\setup\v34-panel-status.py' -WorkingDirectory 'C:\xiaoqian\app\wechat'
$principal=New-ScheduledTaskPrincipal -UserId 'administrator' -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $task -Action $action -Principal $principal | Out-Null
try {
    Start-ScheduledTask -TaskName $task
    for($i=0;$i -lt 20;$i++){ Start-Sleep -Seconds 2; if(Test-Path -LiteralPath $output){break} }
} finally { Unregister-ScheduledTask -TaskName $task -Confirm:$false }
if (!(Test-Path -LiteralPath $output)) { throw 'panel_probe_output_missing' }
$r=Get-Content -LiteralPath $output -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Output ('panel_exists={0};paused_label={1}' -f $r.panel_exists,$r.paused_label)
if (!$r.panel_exists -or !$r.paused_label) { throw 'panel_paused_unconfirmed' }
