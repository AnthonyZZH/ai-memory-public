param([switch]$Create)
$ErrorActionPreference = 'Stop'
$taskName = 'Xiaoqian-Library-Main-Backup'
$zone = Get-TimeZone
if ($zone.Id -ne 'AUS Eastern Standard Time') { throw 'TIMEZONE_MISMATCH: daily trigger requires Melbourne system timezone' }
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$runtimeRoot = 'E:\AI-Library-Backups\_scripts'
$runner = Join-Path $runtimeRoot 'run-backup.ps1'
$powershell = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
$description = 'Pull main vault from ssh library-host into new verified versions in E:\AI-Library-Backups. Daily Melbourne20:00 and logon catch-up. No password, original overwrite, deletion, cloud or model calls.'
$spec = [ordered]@{ Name=$taskName; User=$identity.Name; SID=$identity.User.Value; Timezone=$zone.Id; Daily='20:00'; CatchUp='At user logon and StartWhenAvailable'; Retries='3 retries at 30-minute intervals on failure'; Runner=$runner; LogonType='Interactive'; RunLevel='Limited' }
$spec | ConvertTo-Json
if (-not $Create) { return }
if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) { throw 'STABLE_RUNTIME_MISSING: deploy runtime scripts first' }
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { throw 'TASK_ALREADY_EXISTS: refusing overwrite' }
$action = New-ScheduledTaskAction -Execute $powershell -Argument ('-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File "' + $runner + '"') -WorkingDirectory $runtimeRoot
$daily = New-ScheduledTaskTrigger -Daily -At '20:00'
$logon = New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
$principal = New-ScheduledTaskPrincipal -UserId $identity.User.Value -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 30) -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -Description $description -Action $action -Trigger @($daily, $logon) -Principal $principal -Settings $settings | Select-Object TaskName,State
