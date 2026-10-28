# 计划任务实际走 run_task.py，本文件只供手动调试；改端口两处同改。
# 计划任务 End 不会结束子进程 basic-memory.exe，要停服务需按 PID 结束进程树。
$ErrorActionPreference = 'Stop'
$env:BASIC_MEMORY_NO_PROMOS = '1'
$env:HF_HUB_OFFLINE = '1'
$env:FASTEMBED_CACHE_DIR = 'E:\AI-Memory\cache\fastembed'
$env:TEMP = 'E:\AI-Memory\cache\tmp'
$env:TMP = $env:TEMP
Set-Location 'E:\AI-Memory'
& 'E:\AI-Memory\bin\basic-memory.exe' mcp --transport streamable-http --host 127.0.0.1 --port 8767 --path /mcp --project main
exit $LASTEXITCODE