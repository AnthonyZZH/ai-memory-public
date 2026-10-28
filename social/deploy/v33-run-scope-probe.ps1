$ErrorActionPreference='Stop'
& 'C:\Program Files\nodejs\node.exe' 'C:\xiaoqian\setup\v33-foreground-scope.cjs'
if ($LASTEXITCODE -ne 0) { throw 'scope_probe_process_failed' }
$p='C:\xiaoqian\data\qq\v33-audit\scope-probe-after-link.json'
if (-not (Test-Path -LiteralPath $p)) { throw 'scope_probe_result_missing' }
$d=Get-Content -Raw -LiteralPath $p -Encoding UTF8 | ConvertFrom-Json
Write-Output ("host_scope={0} profile_scope={1} restrict_ok={2} reason={3} create={4}" -f $d.hostScope,$d.profileScope,$d.emptyRestrict,$d.reason,$d.createError)
