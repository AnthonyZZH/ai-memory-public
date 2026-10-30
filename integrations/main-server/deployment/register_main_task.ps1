$ErrorActionPreference='Stop'
$taskName='Xiaoqian-Main-Library'
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { throw 'TASK_ALREADY_EXISTS' }
$taskRoot='C:\AI-Library\main'
if (-not (Test-Path -LiteralPath "$taskRoot\state\config.json")) { throw 'CONFIG_MISSING' }
$identity=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action=New-ScheduledTaskAction -Execute "$taskRoot\venv\Scripts\python.exe" -Argument 'C:\AI-Library\main\run_library.py' -WorkingDirectory $taskRoot
$principal=New-ScheduledTaskPrincipal -UserId $identity -LogonType S4U -RunLevel Limited
$trigger=New-ScheduledTaskTrigger -AtStartup
$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 3 -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$task=New-ScheduledTask -Action $action -Principal $principal -Trigger $trigger -Settings $settings -Description 'Owner main library only; 127.0.0.1:8767; isolated state; no credentials or private library.'
Register-ScheduledTask -TaskName $taskName -InputObject $task | Out-Null
Start-ScheduledTask -TaskName $taskName
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State,@{n='User';e={$_.Principal.UserId}},@{n='LogonType';e={$_.Principal.LogonType}},@{n='RunLevel';e={$_.Principal.RunLevel}}
