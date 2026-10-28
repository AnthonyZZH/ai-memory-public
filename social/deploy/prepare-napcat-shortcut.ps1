$ErrorActionPreference='Stop'
$ids=@(Get-ChildItem -LiteralPath (Join-Path $env:USERPROFILE 'Documents\Tencent Files') -Directory | Where-Object {$_.Name -match '^\d{5,}$'})
if ($ids.Count -ne 1) { throw 'qq_account_directory_not_unique' }
$link='C:\xiaoqian\setup\NapCat-QuickLogin.lnk'
if (Test-Path -LiteralPath $link) { throw 'shortcut_exists' }
$shell=New-Object -ComObject WScript.Shell
$shortcut=$shell.CreateShortcut($link)
$shortcut.TargetPath='C:\xiaoqian\app\napcat\launcher.bat'
$shortcut.Arguments=$ids[0].Name
$shortcut.WorkingDirectory='C:\xiaoqian\app\napcat'
$shortcut.Save()
& icacls.exe $link /inheritance:r /grant:r '*S-1-5-32-544:(F)' '*S-1-5-18:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'shortcut_acl_failed' }
Write-Output 'napcat_quick_login_shortcut_created_account_redacted_not_started'
