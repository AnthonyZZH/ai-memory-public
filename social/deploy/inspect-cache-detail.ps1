$ErrorActionPreference='Stop'
$wxRoot=Join-Path $env:USERPROFILE 'Documents\WeChat Files'
$qqRoot=Join-Path $env:USERPROFILE 'Documents\Tencent Files'
foreach ($dir in Get-ChildItem -LiteralPath $wxRoot -Directory -Force | Where-Object {$_.Name -match '^wxid_'}) {
  $p=Join-Path $dir.FullName 'FileStorage'
  if (Test-Path -LiteralPath $p) { Get-ChildItem -Directory -Force -LiteralPath $p | Select-Object @{n='Type';e={'WeChat FileStorage'}},Name | Format-Table -AutoSize }
}
foreach ($dir in Get-ChildItem -LiteralPath $qqRoot -Directory -Force | Where-Object {$_.Name -match '^\d{5,}$'}) {
  $p=Join-Path $dir.FullName 'nt_qq'
  if (Test-Path -LiteralPath $p) { Get-ChildItem -Directory -Force -LiteralPath $p | Select-Object @{n='Type';e={'QQ nt_qq'}},Name | Format-Table -AutoSize }
}
