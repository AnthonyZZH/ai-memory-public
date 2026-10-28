$ErrorActionPreference='Stop'
$env:DSH_HOME='C:\xiaoqian\data\qq\dsh-home'
$env:DSH_TELEMETRY_DISABLED='1'
$node='C:\Program Files\nodejs\node.exe'
$cli='C:\xiaoqian\app\dsh\node_modules\@deepseek-ai\dsh\lib\bin.js'
$python='C:\xiaoqian\app\wechat\.venv\Scripts\python.exe'
$dump=@(& $node $cli --profile qq-social --dump-config)
if ($LASTEXITCODE -ne 0) { throw 'dsh_dump_failed' }
$dump | & $python -B -X utf8 'C:\xiaoqian\setup\summarize-qq-config.py'
if ($LASTEXITCODE -ne 0) { throw 'dsh_dump_summary_failed' }
