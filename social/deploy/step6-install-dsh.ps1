$ErrorActionPreference='Stop'
$target='C:\xiaoqian\app\dsh'
$tar='C:\xiaoqian\setup\dsh-0.2.1-rc.4.tgz'
if (Test-Path -LiteralPath $target) { throw 'dsh_target_exists' }
if ((Get-FileHash -LiteralPath $tar -Algorithm SHA256).Hash -ne '1FDDEAD34D3C943B7A4EED1D614E14FA19925803455E28C5141645CAF4B02D13') { throw 'dsh_tarball_hash_mismatch' }
New-Item -ItemType Directory -Path $target | Out-Null
$env:DSH_HOME='C:\xiaoqian\data\qq\dsh-home'
$env:DSH_TELEMETRY_DISABLED='1'
& npm.cmd install --prefix $target --ignore-scripts --no-audit --no-fund $tar
if ($LASTEXITCODE -ne 0) { throw 'npm_install_failed' }
$package=Join-Path $target 'node_modules\@deepseek-ai\dsh\package.json'
if (-not (Test-Path $package)) { throw 'dsh_package_missing' }
$meta=Get-Content -Raw -Encoding UTF8 $package | ConvertFrom-Json
if ($meta.version -ne '0.2.1-rc.4') { throw 'dsh_version_mismatch' }
if (-not (Test-Path (Join-Path $target 'package-lock.json'))) { throw 'dsh_lock_missing' }
Write-Output 'dsh_rc4_package_installed_lock_created_not_started'
