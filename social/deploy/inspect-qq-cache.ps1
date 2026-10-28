$ErrorActionPreference='Stop'
$root=Join-Path $env:USERPROFILE 'Documents\Tencent Files'
$ids=@(Get-ChildItem -LiteralPath $root -Directory | Where-Object {$_.Name -match '^\d{5,}$'})
if ($ids.Count -ne 1) { throw 'qq_account_directory_not_unique' }
foreach ($name in @('nt_data','nt_temp')) {
 $p=Join-Path $ids[0].FullName "nt_qq\$name"
 if (Test-Path -LiteralPath $p) { Get-ChildItem -Directory -Force -LiteralPath $p | Select-Object @{n='Category';e={$name}},Name | Format-Table -AutoSize }
}
