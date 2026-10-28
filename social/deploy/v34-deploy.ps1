$ErrorActionPreference='Stop'
$setup='C:\xiaoqian\setup'; $app='C:\xiaoqian\app\wechat'; $backup=Join-Path $setup 'v34-panel-backup'
$archive=Join-Path $setup 'v34-package.zip'; $manifestPath=Join-Path $setup 'v34-manifest.json'; $stage=Join-Path $setup 'v34-package'
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne '3C056A490CE2606AC5731BC0B27BEE1574A792EFC597A6FF3E8751B8A2820781') { throw 'archive_hash_mismatch' }
if ((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash -ne 'DC6F04A7CDD8DF07F2B0061BFBC57717758AA2E8AC81BBF57EB483B9116D6EF7') { throw 'manifest_hash_mismatch' }
if (Test-Path -LiteralPath $backup) { throw 'backup_exists' }
$stickers=@(Get-ChildItem -LiteralPath 'C:\xiaoqian\data\wechat\stickers' -File)
if ($stickers.Count -ne 215 -or !(Test-Path -LiteralPath 'C:\xiaoqian\data\wechat\stickers\index.json')) { throw 'sticker_preflight_not_ready' }
$parsed=Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestPath | ConvertFrom-Json
$items=@($parsed)
if (!(Test-Path -LiteralPath $stage)) { Expand-Archive -LiteralPath $archive -DestinationPath $stage }
foreach ($item in $items) {
    if ($item.file -notin @('app.py','runner.py','social_brain.py','settings.py','owner_relay.py')) { throw 'manifest_filename_rejected' }
    $old=Join-Path $app $item.file; $new=Join-Path $stage $item.file
    if ((Get-FileHash -LiteralPath $new -Algorithm SHA256).Hash -ne $item.after) { throw 'candidate_hash_mismatch' }
    if ($item.before) {
        if (!(Test-Path -LiteralPath $old) -or (Get-FileHash -LiteralPath $old -Algorithm SHA256).Hash -ne $item.before) { throw 'installed_hash_mismatch' }
    } elseif (Test-Path -LiteralPath $old) { throw 'new_file_already_exists' }
}
$panels=@(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -match '(?i)(?:^|[\\/\s"''])app\.py(?:[\s"'']|$)' })
if ($panels.Count -ne 2 -or @($panels | Where-Object SessionId -ne 2).Count -ne 0 -or @($panels | Where-Object { $_.ExecutablePath -eq 'C:\xiaoqian\app\wechat\.venv\Scripts\pythonw.exe' }).Count -ne 1) { throw 'panel_process_topology_unexpected' }
$launcher=@($panels | Where-Object { $_.ExecutablePath -eq 'C:\xiaoqian\app\wechat\.venv\Scripts\pythonw.exe' })[0]
if (@($panels | Where-Object { $_.ParentProcessId -eq $launcher.ProcessId }).Count -ne 1) { throw 'panel_parent_child_mismatch' }
foreach ($process in $panels) { Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
if (@(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -match '(?i)(?:^|[\\/\s"''])app\.py(?:[\s"'']|$)' }).Count) { throw 'panel_still_running' }
New-Item -ItemType Directory -Path $backup | Out-Null
foreach ($item in $items) {
    if ($item.before) { Copy-Item -LiteralPath (Join-Path $app $item.file) -Destination (Join-Path $backup $item.file) }
}
foreach ($item in $items) {
    Copy-Item -LiteralPath (Join-Path $stage $item.file) -Destination (Join-Path $app $item.file) -Force
    if ((Get-FileHash -LiteralPath (Join-Path $app $item.file) -Algorithm SHA256).Hash -ne $item.after) { throw 'installed_verification_failed' }
}
Write-Output 'v34_files_installed_verified_panel_stopped'
