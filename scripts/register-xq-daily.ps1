[CmdletBinding(SupportsShouldProcess = $true)]
param([string]$TaskName = 'XiaoQianDaily')

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root 'tools\xq-engine\Scripts\pythonw.exe'
$script = Join-Path $PSScriptRoot 'xq-daily.py'
$config = Join-Path $root 'config\engine.yaml'
foreach ($path in @($python, $script, $config)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Daily runner files are missing.' }
}
$arguments = '-B -X utf8 "{0}" --config "{1}"' -f $script, $config
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At '03:00'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 6) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
if ($PSCmdlet.ShouldProcess($TaskName, 'Register daily local memory task (03:00, StartWhenAvailable)')) {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Description 'Local-only memory and personality evolution' -Force | Out-Null
}
