$ErrorActionPreference='Stop'
$destination='C:\xiaoqian\setup\QQ_9.9.33_260813_x64_01.exe'
if (Test-Path -LiteralPath $destination) { throw 'qq_installer_already_exists' }
$url='https://qqdl.gtimg.cn/qqfile/QQNT/9.9.33/release/497e2f1f/QQ_9.9.33_260813_x64_01.exe'
& curl.exe -fL --connect-timeout 20 --max-time 300 -o $destination $url
if ($LASTEXITCODE -ne 0) { throw 'qq_download_failed' }
$sig=Get-AuthenticodeSignature -LiteralPath $destination
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch '^CN=Tencent') { throw 'qq_authenticode_invalid' }
Write-Output 'qq_authenticode_tencent_valid'
Write-Output "qq_sha256=$((Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash)"
Write-Output "qq_fileversion=$((Get-Item -LiteralPath $destination).VersionInfo.FileVersion)"
