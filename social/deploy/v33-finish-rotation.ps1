$ErrorActionPreference='Stop'
$path='C:\xiaoqian\app\napcat\config\webui.json'
$tmp='C:\xiaoqian\app\napcat\config\webui.rotation.tmp'
if (-not (Test-Path -LiteralPath $tmp)) { throw 'rotation_temp_missing' }
$before=Get-Content -Raw -LiteralPath $path -Encoding UTF8 | ConvertFrom-Json
$after=Get-Content -Raw -LiteralPath $tmp -Encoding UTF8 | ConvertFrom-Json
if ($before.host -ne '127.0.0.1' -or $after.host -ne '127.0.0.1' -or $after.token.Length -ne 64 -or $before.token -eq $after.token) { throw 'rotation_precheck_failed' }
Move-Item -LiteralPath $tmp -Destination $path -Force
& icacls.exe $path /inheritance:r /grant:r '*S-1-5-32-544:(F)' '*S-1-5-18:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'rotation_acl_failed' }
$check=Get-Content -Raw -LiteralPath $path -Encoding UTF8 | ConvertFrom-Json
if ($check.token -ne $after.token) { throw 'rotation_readback_failed' }
Write-Output 'webui_token_rotated_32_bytes_redacted_restart_required'
