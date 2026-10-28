$ErrorActionPreference='Stop'
$path='C:\xiaoqian\app\napcat\config\webui.json'
if (Test-Path -LiteralPath $path) { throw 'webui_config_exists' }
$bytes=New-Object byte[] 32
$rng=[Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($bytes); $token=([BitConverter]::ToString($bytes)).Replace('-','').ToLowerInvariant() } finally { $rng.Dispose() }
$config=[ordered]@{host='127.0.0.1';port=6099;token=$token;loginRate=10;autoLoginAccount='';theme=@{dark=@{};light=@{};fontMode='system'};disableWebUI=$false;accessControlMode='whitelist';ipWhitelist=@('127.0.0.1');ipBlacklist=@();enableXForwardedFor=$false;enable2FA=$false;totpSecret=''}
$json=ConvertTo-Json -InputObject $config -Depth 10
[IO.File]::WriteAllText($path,$json,(New-Object Text.UTF8Encoding($false)))
& icacls.exe $path /inheritance:r /grant:r '*S-1-5-32-544:(F)' '*S-1-5-18:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'webui_acl_failed' }
$check=Get-Content -Raw -LiteralPath $path -Encoding UTF8 | ConvertFrom-Json
if ($check.host -ne '127.0.0.1' -or $check.token.Length -ne 64 -or $check.accessControlMode -ne 'whitelist') { throw 'webui_config_validation_failed' }
Write-Output 'webui_local_config_written_token_redacted'
