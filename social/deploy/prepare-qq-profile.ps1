$ErrorActionPreference='Stop'
$archive='C:\xiaoqian\setup\dsh-napcat-patched.zip'
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne '5567CB337D30A857C0E0CF08407817E8635ABD58AA286A05D451A857715DCA56') { throw 'plugin_archive_hash_mismatch' }
$vendor='C:\xiaoqian\app\vendor\dsh-napcat'
$profile='C:\xiaoqian\data\qq\dsh-home\profiles\qq-social'
if ((Test-Path -LiteralPath $vendor) -or (Test-Path -LiteralPath $profile)) { throw 'profile_or_vendor_exists' }
New-Item -ItemType Directory -Force -Path $vendor,$profile | Out-Null
Expand-Archive -LiteralPath $archive -DestinationPath $vendor
if (-not (Test-Path -LiteralPath (Join-Path $vendor 'lib\social-policy.js'))) { throw 'patched_plugin_missing' }
$manifest=[ordered]@{name='qq-social';version='1.0.0';private=$true;dependencies=[ordered]@{'dsh-napcat'='file:C:/xiaoqian/app/vendor/dsh-napcat';'@deepseek-ai/cordis'='4.0.5';'@deepseek-ai/schemastery'='3.18.5';'@deepseek-ai/dsh-agent'='0.2.1-rc.4';'@deepseek-ai/dsh-attachment'='0.2.1-rc.4';'@deepseek-ai/dsh-llm'='0.2.1-rc.4';'@deepseek-ai/dsh-session'='0.2.1-rc.4';'@deepseek-ai/dsh-tools'='0.2.1-rc.4'};dsh=@{profile=@{bundles=@('@deepseek-ai/dsh-base','@deepseek-ai/dsh-web-app','dsh-napcat')}}}
[IO.File]::WriteAllText((Join-Path $profile 'package.json'),($manifest | ConvertTo-Json -Depth 12),(New-Object Text.UTF8Encoding($false)))
& npm.cmd install --prefix $profile --ignore-scripts --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'profile_npm_install_failed' }
if (-not (Test-Path -LiteralPath (Join-Path $profile 'package-lock.json'))) { throw 'profile_lock_missing' }
Write-Output 'qq_profile_plugin_installed_and_locked_not_started'
