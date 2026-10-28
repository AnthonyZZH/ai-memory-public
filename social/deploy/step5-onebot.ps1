$ErrorActionPreference='Stop'
$root=Join-Path $env:USERPROFILE 'Documents\Tencent Files'
$ids=@(Get-ChildItem -LiteralPath $root -Directory -Force | Where-Object {$_.Name -match '^\d{5,}$'})
if ($ids.Count -ne 1) { throw 'qq_account_directory_not_unique' }
$configPath=Join-Path 'C:\xiaoqian\app\napcat\config' ('onebot11_'+$ids[0].Name+'.json')
if (Test-Path -LiteralPath $configPath) { throw 'onebot_config_already_exists' }
$web=Get-Content -Raw -Encoding UTF8 -LiteralPath 'C:\xiaoqian\app\napcat\config\webui.json' | ConvertFrom-Json
$bytes=New-Object byte[] 32; $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($bytes); $token=([BitConverter]::ToString($bytes)).Replace('-','').ToLowerInvariant() } finally { $rng.Dispose() }
if ($token -eq $web.token) { throw 'independent_token_generation_failed' }
$config=[ordered]@{network=[ordered]@{httpServers=@();httpSseServers=@();httpClients=@();websocketServers=@(@{name='qq-social';enable=$true;host='127.0.0.1';port=3001;messagePostFormat='array';reportSelfMessage=$false;token=$token;enableForcePushEvent=$true;debug=$false;heartInterval=30000});websocketClients=@();plugins=@()};musicSignUrl='';enableLocalFile2Url=$false;parseMultMsg=$false;imageDownloadProxy='';timeout=@{baseTimeout=10000;uploadSpeedKBps=256;downloadSpeedKBps=256;maxTimeout=1800000}}
[IO.File]::WriteAllText($configPath,($config | ConvertTo-Json -Depth 12),(New-Object Text.UTF8Encoding($false)))
& icacls.exe $configPath /inheritance:r /grant:r '*S-1-5-32-544:(F)' '*S-1-5-18:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'onebot_acl_failed' }
$check=Get-Content -Raw -Encoding UTF8 -LiteralPath $configPath | ConvertFrom-Json
if ($check.network.websocketServers.Count -ne 1 -or $check.network.websocketServers[0].host -ne '127.0.0.1' -or $check.network.websocketServers[0].token.Length -ne 64) { throw 'onebot_config_check_failed' }
Write-Output 'onebot_account_config_created_local_bind_independent_token_redacted'
