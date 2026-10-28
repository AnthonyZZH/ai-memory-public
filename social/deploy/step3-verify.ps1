$ErrorActionPreference='Stop'
$items=@(
  @('C:\xiaoqian\data\shared\persona-social.txt','088eb94076a69b8e8407d13265513c7efa1337453f04e1158be671ef15216350'),
  @('C:\xiaoqian\setup\NapCat.Shell.v4.18.41.zip','6801f93e533846cea05f4f531874a0e84371ab2331c5585b57cd7e3b869cf96b'),
  @('C:\xiaoqian\setup\wechat-patched.zip','cb0354ddb5766407a93e2c16ec1566d4d0303686b19ccc07b5af5c82eed8fe6f'),
  @('C:\xiaoqian\setup\WeChatSetup.exe','c29fc05630cfc95ef6483f6b5b52aabfe74265bb260e210e78ae437d305d8990'),
  @('C:\xiaoqian\setup\dsh-0.2.1-rc.4.tgz','1fddead34d3c943b7a4eed1d614e14fa19925803455e28c5141645caf4b02d13')
)
foreach ($item in $items) {
    if ((Get-FileHash -LiteralPath $item[0] -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item[1]) { throw 'asset_hash_mismatch' }
    Write-Output "verified: $([IO.Path]::GetFileName($item[0]))"
}
$sig=Get-AuthenticodeSignature 'C:\xiaoqian\setup\WeChatSetup.exe'
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch '^CN=Tencent Technology \(Shenzhen\) Company Limited,') { throw 'wechat_signature_invalid' }
Write-Output 'wechat_tencent_authenticode_valid'
