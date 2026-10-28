$ErrorActionPreference='Stop'
$path='C:\xiaoqian\logs\dsh-qq-social-debug.log'
$text=[IO.File]::ReadAllText($path,[Text.Encoding]::UTF8)
Write-Output ("log_characters={0}" -f $text.Length)
foreach ($line in $text -split "`r?`n") {
 if ($line -match '(?i)error|failed|fatal|exception|listening|127\.0\.0\.1|ready|napcat|profile|timeout|foreground_exit') {
  $safe=$line -replace '(?i)(token|authorization|secret|api.?key)\s*[:=]\s*\S+','$1=[REDACTED]' -replace '\b[A-Za-z0-9+/=_-]{40,}\b','[REDACTED]'
  Write-Output $safe
 }
}
