$ErrorActionPreference='Stop'
& 'C:\Program Files\nodejs\node.exe' 'C:\xiaoqian\setup\v33-foreground-paired.cjs'
if ($LASTEXITCODE -ne 0) { throw 'paired_runtime_process_failed' }
$p='C:\xiaoqian\data\qq\v33-audit\paired-runtime.json'
if (-not (Test-Path -LiteralPath $p)) { throw 'paired_runtime_result_missing' }
$rows=@(Get-Content -Raw -LiteralPath $p -Encoding UTF8 | ConvertFrom-Json)
foreach ($row in $rows) { Write-Output ("{0}: ok={1}; error={2}; tool_count={3}" -f $row.label,$row.ok,$row.error,@($row.tools).Count); foreach ($name in $row.tools) { if ($name -notmatch '^[A-Za-z0-9_.-]{1,100}$') { throw 'tool_name_invalid' }; Write-Output "tool=$name" } }
if ($rows.Count -ne 2 -or $rows[0].ok -or -not $rows[1].ok) { throw 'paired_runtime_expectation_failed' }
