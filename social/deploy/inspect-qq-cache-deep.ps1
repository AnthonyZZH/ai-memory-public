$ErrorActionPreference='Stop'
$roots=@((Join-Path $env:USERPROFILE 'Documents\Tencent Files'),(Join-Path $env:APPDATA 'Tencent\QQ'),(Join-Path $env:APPDATA 'Tencent\QQNT'),(Join-Path $env:LOCALAPPDATA 'Tencent'))
foreach ($root in $roots) {
 if (-not (Test-Path -LiteralPath $root)) { continue }
 $queue=New-Object 'System.Collections.Generic.Queue[object]'; $queue.Enqueue(@($root,0))
 while ($queue.Count) {
  $entry=$queue.Dequeue(); $dir=[string]$entry[0]; $depth=[int]$entry[1]
  if ($depth -ge 5) { continue }
  foreach ($child in @(Get-ChildItem -LiteralPath $dir -Directory -Force -ErrorAction SilentlyContinue)) {
    if ($child.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
    $clean=$child.FullName -replace '\\[0-9]{5,}(?=\\|$)','\<account>' -replace '\\wxid_[^\\]+','\<account>'
    if ($child.Name -match '(?i)cache|image|pic|video|media|thumb|file') { Write-Output $clean }
    $queue.Enqueue(@($child.FullName,($depth+1)))
  }
 }
}
