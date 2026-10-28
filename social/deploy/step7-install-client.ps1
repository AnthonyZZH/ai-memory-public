$ErrorActionPreference='Stop'
$installer='C:\xiaoqian\setup\WeChatSetup.exe'
if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ne 'C29FC05630CFC95EF6483F6B5B52AABFE74265BB260E210E78AE437D305D8990') { throw 'wechat_installer_hash_mismatch' }
$sig=Get-AuthenticodeSignature -LiteralPath $installer
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch '^CN=Tencent') { throw 'wechat_installer_signature_invalid' }
$keys=@('HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\WeChat','HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\WeChat')
if (@($keys | Where-Object {Test-Path -LiteralPath $_}).Count) { throw 'wechat_already_installed' }
$p=Start-Process -FilePath $installer -ArgumentList '/S' -PassThru
if (-not $p.WaitForExit(180000)) { throw 'wechat_installer_timeout_process_not_killed' }
if ($p.ExitCode -ne 0) { throw "wechat_installer_failed:$($p.ExitCode)" }
$found=@($keys | Where-Object {Test-Path -LiteralPath $_})
if (-not $found.Count) { throw 'wechat_uninstall_registry_missing' }
$reg=Get-ItemProperty -LiteralPath $found[0]
Write-Output "wechat_installed_displayversion=$($reg.DisplayVersion)"
