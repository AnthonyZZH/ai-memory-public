$ErrorActionPreference='Stop'
$rows=Get-Content -Raw -LiteralPath 'C:\xiaoqian\data\qq\v33-audit\paired-runtime.json' -Encoding UTF8 | ConvertFrom-Json
foreach ($row in $rows) { Write-Output ("{0}: ok={1}; error={2}; tool_count={3}" -f $row.label,$row.ok,$row.error,@($row.tools).Count); foreach ($name in $row.tools) { if ($name -notmatch '^[A-Za-z0-9_.-]{1,100}$') { throw 'tool_name_invalid' }; Write-Output "tool=$name" } }
