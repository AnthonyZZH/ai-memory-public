$ErrorActionPreference='Stop'
$profile='C:\xiaoqian\data\qq\dsh-home\profiles\qq-social'
$source=Join-Path $profile 'node_modules\@deepseek-ai\dsh-scope'
$target='C:\xiaoqian\app\dsh\node_modules\@deepseek-ai\dsh-scope'
$backup='C:\xiaoqian\setup\v33-dsh-scope-npm-restored'
if (-not (Test-Path -LiteralPath $source -PathType Container) -or -not (Test-Path -LiteralPath $target -PathType Container) -or (Test-Path -LiteralPath $backup)) { throw 'scope_repair_precheck_failed' }
$item=Get-Item -Force -LiteralPath $source
if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'scope_already_linked' }
Move-Item -LiteralPath $source -Destination $backup
New-Item -ItemType Junction -Path $source -Target $target | Out-Null
$item=Get-Item -Force -LiteralPath $source
if(-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'scope_repair_failed'}
$build='C:\xiaoqian\setup\v33-final-plugin-build'
foreach($file in @('lib\social-policy.js','lib\bridge.js','lib\tools.js')) {
 if((Get-FileHash -LiteralPath (Join-Path $build $file) -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath (Join-Path $profile "node_modules\dsh-napcat\$file") -Algorithm SHA256).Hash){throw 'plugin_digest_mismatch'}
}
Write-Output 'scope_junction_restored_npm_copy_preserved_final_plugin_hashes_match'
