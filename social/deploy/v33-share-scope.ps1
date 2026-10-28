$ErrorActionPreference='Stop'
$source='C:\xiaoqian\data\qq\dsh-home\profiles\qq-social\node_modules\@deepseek-ai\dsh-scope'
$target='C:\xiaoqian\app\dsh\node_modules\@deepseek-ai\dsh-scope'
$backup='C:\xiaoqian\setup\v33-dsh-scope-profile-original'
if (-not (Test-Path -LiteralPath $source -PathType Container) -or -not (Test-Path -LiteralPath $target -PathType Container) -or (Test-Path -LiteralPath $backup)) { throw 'scope_link_precheck_failed' }
$sourceItem=Get-Item -Force -LiteralPath $source
if ($sourceItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'scope_source_already_linked' }
$active=@(Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object {$_.CommandLine -like '*qq-social*'})
if ($active.Count -ne 0) { throw 'qq_social_running' }
Move-Item -LiteralPath $source -Destination $backup
New-Item -ItemType Junction -Path $source -Target $target | Out-Null
$item=Get-Item -Force -LiteralPath $source
if (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'scope_link_verification_failed' }
Write-Output 'scope_package_shared_junction_original_preserved'
