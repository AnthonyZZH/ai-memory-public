$ErrorActionPreference='Stop'
$src='C:\xiaoqian\setup\wechat-patched.zip'
$dst='C:\xiaoqian\app\wechat'
$data='C:\xiaoqian\data\wechat'
if ((Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash -ne 'CB0354DDB5766407A93E2C16EC1566D4D0303686B19CCC07B5AF5C82EED8FE6F') { throw 'wechat_archive_hash_mismatch' }
if (@(Get-ChildItem -Force -LiteralPath $dst).Count -ne 0 -or @(Get-ChildItem -Force -LiteralPath $data).Count -ne 0) { throw 'wechat_directory_not_empty' }
& icacls.exe $data /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'wechat_data_acl_failed' }
Expand-Archive -LiteralPath $src -DestinationPath $dst
if (-not (Test-Path -LiteralPath (Join-Path $dst 'app.py'))) { throw 'wechat_app_missing' }
Write-Output 'wechat_patched_source_extracted_data_acl_restricted'
