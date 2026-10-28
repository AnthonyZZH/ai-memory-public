$ErrorActionPreference='Stop'
& 'C:\Program Files\nodejs\node.exe' 'C:\xiaoqian\setup\v33-foreground-final.cjs'
if ($LASTEXITCODE -ne 0) { throw 'final_audit_process_failed' }
$p='C:\xiaoqian\data\qq\v33-audit\tool-audit-final.json'
if(-not (Test-Path -LiteralPath $p)){throw 'final_audit_missing'}
$d=Get-Content -Raw -LiteralPath $p -Encoding UTF8 | ConvertFrom-Json
if(-not $d.ok){Write-Output ("final_audit_error={0}" -f $d.reason);throw 'final_audit_failed'}
$names=@($d.tools);Write-Output ("final_runtime_scope={0};tool_count={1}" -f $d.scope,$names.Count)
foreach($name in $names){if($name -notmatch '^[A-Za-z0-9_.-]{1,100}$'){throw 'invalid_tool_name'};Write-Output "tool=$name"}
if($names.Count -ne 0){throw 'unexpected_tool_registered'}
