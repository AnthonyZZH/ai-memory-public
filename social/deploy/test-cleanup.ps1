$ErrorActionPreference='Stop'
$base='E:\Codex Development\tmp\v3.2-cleanup-test'
if (Test-Path -LiteralPath $base) { throw 'test directory exists' }
New-Item -ItemType Directory -Path $base | Out-Null
$source=Get-Content -Raw -Encoding UTF8 'E:\AI-Memory\social\deploy\cleanup.ps1'
$paths=@('C:\xiaoqian\data\qq\media-cache','C:\xiaoqian\data\wechat\media-cache','C:\xiaoqian\logs')
for ($i=0; $i -lt $paths.Count; $i++) { $source=$source.Replace($paths[$i], (Join-Path $base "policy$i")) }
$fixture=Join-Path $base 'cleanup-fixture.ps1'
[IO.File]::WriteAllText($fixture,$source,(New-Object Text.UTF8Encoding($false)))
for ($i=0; $i -lt 3; $i++) {
  $dir=Join-Path $base "policy$i"; New-Item -ItemType Directory $dir | Out-Null
  $old=Join-Path $dir 'old.txt'; $new=Join-Path $dir 'new.txt'
  [IO.File]::WriteAllText($old,'old'); [IO.File]::WriteAllText($new,'new')
  (Get-Item $old).LastWriteTimeUtc=[DateTime]::UtcNow.AddDays(-20)
}
$result=@(& $fixture)
if (($result | Where-Object Action -eq 'would-delete').Count -ne 3) { throw 'dry_run_count_failed' }
if (-not (Test-Path (Join-Path $base 'policy0\old.txt'))) { throw 'dry_run_deleted_file' }
$result=@(& $fixture -Apply)
if (($result | Where-Object Action -eq 'deleted').Count -ne 3) { throw 'apply_count_failed' }
for ($i=0; $i -lt 3; $i++) { if (-not (Test-Path (Join-Path $base "policy$i\new.txt"))) { throw 'new_file_deleted' } }
Write-Output 'cleanup fixture dry-run and apply: passed'
