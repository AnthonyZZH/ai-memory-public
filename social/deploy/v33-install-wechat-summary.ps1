$ErrorActionPreference = 'Stop'
$src = 'C:\xiaoqian\setup\social_brain-v33.py'
$dst = 'C:\xiaoqian\app\wechat\social_brain.py'
$backup = 'C:\xiaoqian\setup\social_brain-before-v33.py'
$old = '5E523183E7B6B1B3E90B3AFBAE7192D88307C511CF7267ABB9041FAE3258DA7D'
$new = 'CC92AD7C58786501248B56C7604622BF3E789AD3EEE45387A3494C072CDA8DB5'
if ((Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash -ne $new) { throw 'source_hash_mismatch' }
if ((Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash -ne $old) { throw 'installed_hash_mismatch' }
if (Test-Path -LiteralPath $backup) { throw 'backup_already_exists' }
$running = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -match '(?i)xiaoqian[\\/]app[\\/]wechat' })
if ($running.Count) { throw 'wechat_runner_may_be_running' }
Copy-Item -LiteralPath $dst -Destination $backup
Copy-Item -LiteralPath $src -Destination $dst -Force
if ((Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash -ne $new) { throw 'installed_hash_verification_failed' }
Write-Output 'wechat_summary_patch_installed_and_verified'
