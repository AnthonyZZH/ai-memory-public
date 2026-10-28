$ErrorActionPreference='Stop'
$p='C:\xiaoqian\data\qq\v33-audit\tool-audit-retry.json'
if (-not (Test-Path -LiteralPath $p)) { throw 'audit_result_missing' }
$d=Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Output ("ok={0}; type={1}; reason={2}; count={3}" -f $d.ok,$d.errorType,$d.reason,@($d.tools).Count)
foreach ($name in $d.tools) { if ($name -notmatch '^[A-Za-z0-9_.-]{1,100}$') { throw 'tool_name_rejected' }; Write-Output ("tool={0}" -f $name) }
