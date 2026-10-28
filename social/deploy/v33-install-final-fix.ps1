$ErrorActionPreference='Stop'
$profile='C:\xiaoqian\data\qq\dsh-home\profiles\qq-social'
$zip='C:\xiaoqian\setup\v33-dsh-napcat-final.zip'
$build='C:\xiaoqian\setup\v33-final-plugin-build'
$dist='C:\xiaoqian\setup\v33-final-plugin-dist'
$backup='C:\xiaoqian\setup\v33-profile-before-final-fix'
foreach($p in @($build,$dist,$backup)) { if(Test-Path -LiteralPath $p){throw 'final_fix_path_exists'} }
if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash -ne '2B5AF5F4C8B66D3AF886BA987FB95F65BCECA712FFFACDDF818273E2703682D4') { throw 'final_zip_digest_mismatch' }
$active=@(Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object {$_.CommandLine -like '*qq-social*'})
if($active.Count){throw 'qq_social_running'}
New-Item -ItemType Directory -Path $build,$dist,$backup | Out-Null
Copy-Item -LiteralPath (Join-Path $profile 'package.json') -Destination $backup
Copy-Item -LiteralPath (Join-Path $profile 'package-lock.json') -Destination $backup
Copy-Item -LiteralPath (Join-Path $profile 'node_modules\dsh-napcat') -Destination (Join-Path $backup 'dsh-napcat') -Recurse
Expand-Archive -LiteralPath $zip -DestinationPath $build
& npm.cmd pack $build --ignore-scripts --pack-destination $dist
if($LASTEXITCODE -ne 0){throw 'candidate_pack_failed'}
$tar=Join-Path $dist 'dsh-napcat-0.3.39.tgz'
& npm.cmd install --prefix $profile --ignore-scripts --no-audit --no-fund $tar
if($LASTEXITCODE -ne 0){throw 'candidate_install_failed'}
foreach($file in @('lib\social-policy.js','lib\bridge.js','lib\tools.js')) {
 $a=(Get-FileHash -LiteralPath (Join-Path $build $file) -Algorithm SHA256).Hash
 $b=(Get-FileHash -LiteralPath (Join-Path $profile "node_modules\dsh-napcat\$file") -Algorithm SHA256).Hash
 if($a -ne $b){throw 'candidate_installed_digest_mismatch'}
}
$scope=Join-Path $profile 'node_modules\@deepseek-ai\dsh-scope';$scopeItem=Get-Item -Force -LiteralPath $scope
if(-not ($scopeItem.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'scope_junction_removed_by_npm'}
Write-Output 'final_patched_plugin_installed_hashes_verified_scope_junction_retained'
