$ErrorActionPreference='Stop'
$zip='C:\xiaoqian\setup\NapCat.Shell.v4.18.41.zip'
$target='C:\xiaoqian\app\napcat'
if ((Get-FileHash $zip -Algorithm SHA256).Hash -ne '6801F93E533846CEA05F4F531874A0E84371AB2331C5585B57CD7E3B869CF96B') { throw 'napcat_hash_mismatch' }
if (@(Get-ChildItem -Force -LiteralPath $target).Count -ne 0) { throw 'napcat_directory_not_empty' }
Expand-Archive -LiteralPath $zip -DestinationPath $target
if (-not (Test-Path -LiteralPath (Join-Path $target 'launcher.bat'))) { throw 'napcat_launcher_missing' }
Write-Output 'napcat_shell_extracted_not_started'
