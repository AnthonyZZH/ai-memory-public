$ErrorActionPreference='Stop'
$root='C:\xiaoqian\data\qq\v33-audit'; $id=[int](Get-Content -LiteralPath (Join-Path $root 'process.id'))
$p=Get-Process -Id $id -ErrorAction SilentlyContinue
Write-Output "test_process_alive=$($null -ne $p)"
if ($p) { Get-NetTCPConnection -State Listen -OwningProcess $id -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort | Format-Table -AutoSize }
foreach ($file in @('stdout.log','stderr.log')) {
 $p=Join-Path $root $file; $text=[IO.File]::ReadAllText($p)
 Write-Output ("{0}: chars={1}, error_marker={2}, profile_marker={3}, listener_marker={4}" -f $file,$text.Length,($text -match '(?i)error|failed|fatal|exception'),($text -match '(?i)profile|napcat'),($text -match '(?i)listening|127\.0\.0\.1:3080|localhost:3080'))
 if ($text -match '(?i)ERR_MODULE_NOT_FOUND') { Write-Output 'marker=ERR_MODULE_NOT_FOUND' }
 if ($text -match '(?i)SOCIAL_GUARD_UNAVAILABLE') { Write-Output 'marker=SOCIAL_GUARD_UNAVAILABLE' }
 if ($text -match '(?i)EADDRINUSE') { Write-Output 'marker=EADDRINUSE' }
}
