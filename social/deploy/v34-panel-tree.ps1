$ErrorActionPreference='Stop'
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -match '(?i)(?:^|[\\/\s"''])app\.py(?:[\s"'']|$)' } | ForEach-Object {
    Write-Output ('pid={0};parent={1};session={2};exe={3}' -f $_.ProcessId,$_.ParentProcessId,$_.SessionId,$_.ExecutablePath)
}
