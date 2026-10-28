$ErrorActionPreference='Stop'
$p='C:\xiaoqian\data\qq\v33-audit\tool-audit.json'
if (-not (Test-Path -LiteralPath $p)) { Write-Output 'runtime_audit_result_missing'; exit 2 }
$d=Get-Content -LiteralPath $p -Encoding UTF8 -Raw | ConvertFrom-Json
if (-not $d.ok) { Write-Output ("runtime_audit_failed_type={0}" -f $d.errorType); exit 1 }
Write-Output ("runtime_scope={0}, tool_count={1}" -f $d.scope,@($d.tools).Count)
foreach ($tool in $d.tools) { if ($tool -notmatch '^[A-Za-z0-9_.-]{1,100}$') { throw 'tool_name_rejected' }; Write-Output ("tool={0}" -f $tool) }
