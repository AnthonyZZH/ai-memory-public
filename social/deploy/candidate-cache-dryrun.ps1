$ErrorActionPreference='Stop'
$wx=@(Get-ChildItem -Directory -LiteralPath 'C:\Users\administrator\Documents\WeChat Files' | Where-Object {$_.Name -match '^wxid_'})
$qq=@(Get-ChildItem -Directory -LiteralPath 'C:\Users\administrator\Documents\Tencent Files' | Where-Object {$_.Name -match '^\d{5,}$'})
if ($wx.Count -ne 1 -or $qq.Count -ne 1) { throw 'account_directory_not_unique' }
$paths=@(@{kind='WeChat candidate Cache';path=(Join-Path $wx[0].FullName 'FileStorage\Cache');days=7},@{kind='QQ candidate dataline thumbnails';path=(Join-Path $qq[0].FullName 'nt_qq\nt_data\dataline\.thumb');days=7},@{kind='application logs';path='C:\xiaoqian\logs';days=14})
foreach ($p in $paths) {
 $count=0; $bytes=0L; $exists=Test-Path -LiteralPath $p.path -PathType Container
 if ($exists) {
  $queue=New-Object 'System.Collections.Generic.Stack[string]'; $queue.Push($p.path)
  while ($queue.Count -gt 0) {
   $dir=$queue.Pop(); $item=Get-Item -LiteralPath $dir -Force
   if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'reparse_point_rejected' }
   foreach ($child in Get-ChildItem -LiteralPath $dir -Force) {
    if ($child.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'reparse_point_rejected' }
    if ($child.PSIsContainer) { $queue.Push($child.FullName); continue }
    if ($child.LastWriteTimeUtc -lt [DateTime]::UtcNow.AddDays(-$p.days)) { $count++; $bytes+=$child.Length }
   }
  }
 }
 Write-Output ("{0}: exists={1}, older_than_days={2}, files={3}, bytes={4}" -f $p.kind,$exists,$p.days,$count,$bytes)
}
Write-Output 'dry_run_only_no_files_deleted_no_task_registered'
