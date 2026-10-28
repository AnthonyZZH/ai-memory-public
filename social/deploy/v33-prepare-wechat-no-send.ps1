$ErrorActionPreference = 'Stop'
$python = 'C:\xiaoqian\app\wechat\.venv\Scripts\pythonw.exe'
$entry = 'C:\xiaoqian\setup\v33-wechat-no-send.py'
$link = 'C:\xiaoqian\setup\WeChat-NoSend-Test.lnk'
if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $entry)) { throw 'test_files_missing' }
if (Test-Path -LiteralPath $link) { throw 'shortcut_exists' }
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = $python
$shortcut.Arguments = '"C:\xiaoqian\setup\v33-wechat-no-send.py"'
$shortcut.WorkingDirectory = 'C:\xiaoqian\app\wechat'
$shortcut.Description = 'One WeChat read-only no-send audit turn'
$shortcut.Save()
& icacls.exe $link /inheritance:r /grant:r '*S-1-5-32-544:(F)' '*S-1-5-18:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'shortcut_acl_failed' }
Write-Output 'wechat_no_send_shortcut_created_not_started'
