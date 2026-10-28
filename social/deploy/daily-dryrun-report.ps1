$ErrorActionPreference='Stop'
$directory='C:\xiaoqian\logs\cleanup-reports'
if (Test-Path -LiteralPath $directory) {
 $item=Get-Item -Force -LiteralPath $directory
 if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'report_directory_reparse_rejected' }
} else { New-Item -ItemType Directory -Path $directory | Out-Null }
$report=Join-Path $directory ('dry-run-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')+'.txt')
try {
 $result=@(& 'C:\xiaoqian\setup\candidate-cache-dryrun.ps1')
 [IO.File]::WriteAllLines($report,[string[]](@('DRY RUN - no deletion; media paths are candidates')+$result),(New-Object Text.UTF8Encoding($false)))
 Write-Output 'daily_dry_run_report_written'
} catch {
 [IO.File]::WriteAllText($report,'DRY RUN FAILED; inspect task and filesystem. No deletion was attempted.',(New-Object Text.UTF8Encoding($false)))
 throw
}
