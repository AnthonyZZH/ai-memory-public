$ErrorActionPreference='Stop'
$task='XiaoqianV34PanelTreeOnce'; $output='C:\xiaoqian\setup\v34-panel-tree-probe.json'
if ((Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue) -or (Test-Path -LiteralPath $output)) { throw 'probe_state_exists' }
$action=New-ScheduledTaskAction -Execute 'C:\xiaoqian\app\wechat\.venv\Scripts\pythonw.exe' -Argument '-B -X utf8 C:\xiaoqian\setup\v34-panel-tree-probe.py' -WorkingDirectory 'C:\xiaoqian\app\wechat'
$principal=New-ScheduledTaskPrincipal -UserId 'administrator' -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $task -Action $action -Principal $principal | Out-Null
try { Start-ScheduledTask -TaskName $task; for($i=0;$i -lt 20;$i++){ Start-Sleep -Seconds 2; if(Test-Path -LiteralPath $output){break} } }
finally { Unregister-ScheduledTask -TaskName $task -Confirm:$false }
if (!(Test-Path -LiteralPath $output)) { throw 'probe_output_missing' }
Get-Content -LiteralPath $output -Raw -Encoding UTF8
