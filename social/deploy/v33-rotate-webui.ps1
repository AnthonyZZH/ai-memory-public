$ErrorActionPreference='Stop'
$path='C:\xiaoqian\app\napcat\config\webui.json'
$tmp='C:\xiaoqian\app\napcat\config\webui.rotation.tmp'
if (Test-Path -LiteralPath $tmp) { throw 'rotation_temp_exists' }
$config=Get-Content -Raw -LiteralPath $path -Encoding UTF8 | ConvertFrom-Json
if ($config.host -ne '127.0.0.1') { throw 'webui_host_not_loopback' }
$old=$config.token
$bytes=New-Object byte[] 32; $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
try {$rng.GetBytes($bytes); $new=([BitConverter]::ToString($bytes)).Replace('-','').ToLowerInvariant()} finally {$rng.Dispose()}
if ($new -eq $old) { throw 'token_rotation_random_collision' }
$config.token=$new
[IO.File]::WriteAllText($tmp,'',(New-Object Text.UTF8Encoding($false)))
& icacls.exe $tmp /inheritance:r /grant:r '*S-1-5-32-544:(F)' '*S-1-5-18:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'rotation_acl_failed' }
[IO.File]::WriteAllText($tmp,($config | ConvertTo-Json -Depth 50),(New-Object Text.UTF8Encoding($false)))
[IO.File]::Replace($tmp,$path,$null)
$check=Get-Content -Raw -LiteralPath $path -Encoding UTF8 | ConvertFrom-Json
if ($check.token -ne $new -or $check.token.Length -ne 64) { throw 'token_rotation_readback_failed' }
Write-Output 'webui_token_rotated_32_bytes_redacted_restart_required'
