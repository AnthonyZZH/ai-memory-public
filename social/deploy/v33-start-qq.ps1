$ErrorActionPreference='Stop'
$env:DSH_HOME='C:\xiaoqian\data\qq\dsh-home'
$env:DSH_TELEMETRY_DISABLED='1'
$root='C:\xiaoqian\data\qq\v33-audit'
if (Test-Path -LiteralPath $root) { throw 'audit_directory_exists' }
New-Item -ItemType Directory -Path $root | Out-Null
& icacls.exe $root /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'audit_acl_failed' }
$node='C:\Program Files\nodejs\node.exe'
$cli='C:\xiaoqian\app\dsh\node_modules\@deepseek-ai\dsh\lib\bin.js'
$proc=Start-Process -FilePath $node -ArgumentList @("`"$cli`"",'--profile','qq-social','--no-open') -WorkingDirectory 'C:\xiaoqian\data\qq' -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'stdout.log') -RedirectStandardError (Join-Path $root 'stderr.log')
[IO.File]::WriteAllText((Join-Path $root 'process.id'),[string]$proc.Id)
Start-Sleep -Seconds 15
$proc.Refresh()
if ($proc.HasExited) { Write-Output "dsh_exited_code=$($proc.ExitCode)"; exit 1 }
$ports=@(Get-NetTCPConnection -State Listen -OwningProcess $proc.Id -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort)
Write-Output "dsh_test_process_started_pid=$($proc.Id)"
$ports | Format-Table -AutoSize
