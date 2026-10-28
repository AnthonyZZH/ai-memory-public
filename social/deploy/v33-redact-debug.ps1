$ErrorActionPreference='Stop'
$p='C:\xiaoqian\logs\dsh-qq-social-debug.log'
$t=[IO.File]::ReadAllText($p,[Text.Encoding]::UTF8)
$t=$t -replace '(?i)([?&]token=)[^\s&#]+','$1[REDACTED]' -replace '(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;"'']+','$1[REDACTED]'
[IO.File]::WriteAllText($p,$t,(New-Object Text.UTF8Encoding($false)))
Write-Output 'existing_debug_log_token_query_redacted'
