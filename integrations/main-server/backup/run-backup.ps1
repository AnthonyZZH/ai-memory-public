param([switch]$Force)
$ErrorActionPreference = 'Stop'
# Windows zone ID for Australia/Melbourne, including daylight saving transitions.
$melbourne = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, 'AUS Eastern Standard Time')
$dueDay = $melbourne.Date
if ($melbourne.Hour -lt 20) { $dueDay = $dueDay.AddDays(-1) }
$python = 'python'
$script = Join-Path $PSScriptRoot 'backup_main.py'
$arguments = @($script, '--due-day', $dueDay.ToString('yyyy-MM-dd'))
if ($Force) { $arguments += '--force' }
& $python @arguments
exit $LASTEXITCODE
