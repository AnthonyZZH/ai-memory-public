$ErrorActionPreference='Stop'
$wxRoot=Join-Path $env:USERPROFILE 'Documents\WeChat Files'
$qqRoot=Join-Path $env:USERPROFILE 'Documents\Tencent Files'
$wx=@(Get-ChildItem -LiteralPath $wxRoot -Directory | Where-Object {$_.Name -match '^wxid_'})
$qq=@(Get-ChildItem -LiteralPath $qqRoot -Directory | Where-Object {$_.Name -match '^\d{5,}$'})
if ($wx.Count -ne 1 -or $qq.Count -ne 1) { throw 'account_directory_not_unique' }
$paths=@(@{label='wechat-cache';path=(Join-Path $wx[0].FullName 'FileStorage\Cache')},@{label='wechat-temp';path=(Join-Path $wx[0].FullName 'FileStorage\Temp')},@{label='qq-nt-temp';path=(Join-Path $qq[0].FullName 'nt_qq\nt_temp')},@{label='qq-nt-data-dataline-thumbs';path=(Join-Path $qq[0].FullName 'nt_qq\nt_data\dataline\.thumb')})
foreach ($entry in $paths) {
 $files=@(Get-ChildItem -LiteralPath $entry.path -File -Recurse -Force -ErrorAction SilentlyContinue)
 $summary=@($files | Group-Object Extension | Sort-Object Count -Descending | Select-Object -First 10 | ForEach-Object { '{0}:{1}' -f $_.Name,$_.Count }) -join ','
 Write-Output ("{0} files={1} extensions={2}" -f $entry.label,$files.Count,$summary)
}
