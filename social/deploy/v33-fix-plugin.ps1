$ErrorActionPreference='Stop'
$profile='C:\xiaoqian\data\qq\dsh-home\profiles\qq-social'
$vendor='C:\xiaoqian\app\vendor\dsh-napcat'
$archive='C:\xiaoqian\setup\dsh-napcat-0.3.39.tgz'
$backup='C:\xiaoqian\setup\v33-profile-before-plugin-fix'
if ((Test-Path -LiteralPath $archive) -or (Test-Path -LiteralPath $backup)) { throw 'fix_backup_or_package_exists' }
New-Item -ItemType Directory -Path $backup | Out-Null
Copy-Item -LiteralPath (Join-Path $profile 'package.json') -Destination $backup
Copy-Item -LiteralPath (Join-Path $profile 'package-lock.json') -Destination $backup
& npm.cmd pack $vendor --ignore-scripts --pack-destination 'C:\xiaoqian\setup'
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $archive)) { throw 'plugin_pack_failed' }
& npm.cmd install --prefix $profile --ignore-scripts --no-audit --no-fund $archive
if ($LASTEXITCODE -ne 0) { throw 'plugin_archive_install_failed' }
$installed=Join-Path $profile 'node_modules\dsh-napcat\lib\social-policy.js'
$original=Join-Path $vendor 'lib\social-policy.js'
if (-not (Test-Path -LiteralPath $installed)) { throw 'plugin_installed_file_missing' }
if ((Get-FileHash $installed -Algorithm SHA256).Hash -ne (Get-FileHash $original -Algorithm SHA256).Hash) { throw 'plugin_patched_file_mismatch' }
$pluginDir=Get-Item -LiteralPath (Join-Path $profile 'node_modules\dsh-napcat') -Force
if ($pluginDir.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'plugin_still_linked' }
$ws=Join-Path $profile 'node_modules\ws\package.json'
if (-not (Test-Path -LiteralPath $ws)) { throw 'ws_dependency_missing' }
Write-Output 'plugin_packaged_installed_ws_present_patch_hash_matches'
