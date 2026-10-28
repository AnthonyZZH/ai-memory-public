$ErrorActionPreference='Stop'
$app='C:\xiaoqian\app\wechat';$data='C:\xiaoqian\data\wechat';$setup='C:\xiaoqian\setup'
$src=Join-Path $setup 'v35-package.zip';$manifestPath=Join-Path $setup 'v35-manifest.json'
$migration=Join-Path $data 'v35-migration-v2.zip';$stage=Join-Path $setup 'v35-package';$incoming=Join-Path $data 'v35-incoming';$backup=Join-Path $data 'v35-before-deploy'
if((Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash -ne 'FAB6FDF24C13C432D4D8C74A0A48D03E965761E5C096893F90F6D5758FEC14E9'){throw 'package_hash_invalid'}
if((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash -ne '77B67D9AB3E49DE3F704B07723C5FEE42544D515787D295B5E3F8239853D3BA9'){throw 'manifest_hash_invalid'}
if((Get-FileHash -LiteralPath $migration -Algorithm SHA256).Hash -ne '722C00AEAB945FA0AAD2F64228399C402529384D8E90F76E130BA570D0532C1E'){throw 'migration_hash_invalid'}
if((Test-Path -LiteralPath $stage) -or (Test-Path -LiteralPath $incoming) -or (Test-Path -LiteralPath $backup)){throw 'deployment_paths_exist'}
$parsed=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json;$items=@($parsed)
Expand-Archive -LiteralPath $src -DestinationPath $stage
Expand-Archive -LiteralPath $migration -DestinationPath $incoming
foreach($item in $items){
    if($item.file -notin @('app.py','runner.py','social_brain.py','settings.py')){throw 'package_name_invalid'}
    if((Get-FileHash -LiteralPath (Join-Path $app $item.file) -Algorithm SHA256).Hash -ne $item.before){throw 'existing_app_hash_mismatch'}
    if((Get-FileHash -LiteralPath (Join-Path $stage $item.file) -Algorithm SHA256).Hash -ne $item.after){throw 'staged_app_hash_mismatch'}
}
$mig=Get-Content -LiteralPath (Join-Path $incoming 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if(@($mig.files).Count -ne 22){throw 'migration_count_invalid'}
if(@($mig.files | Where-Object {$_.reset_cursor -eq $true}).Count -ne 1){throw 'migration_cursor_count_invalid'}
foreach($entry in $mig.files){
    if($entry.kind -notin @('history','memory','senders') -or $entry.filename -notmatch '^[0-9a-f]{64}\.(json|learned)$' -or ($entry.kind -ne 'history' -and $entry.filename -notmatch '\.json$')){throw 'migration_filename_invalid'}
    $file=Join-Path (Join-Path $incoming $entry.kind) $entry.filename
    if((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.sha256){throw 'migration_file_hash_invalid'}
}
foreach($kind in @('history','memory','senders')){
    $dir=Join-Path $data $kind
    if(Test-Path -LiteralPath $dir){
        if((Get-Item -LiteralPath $dir -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'target_reparse_rejected'}
        if(@(Get-ChildItem -LiteralPath $dir -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count){throw 'target_reparse_rejected'}
    }
}
$panels=@(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -match '(?i)(?:^|[\\/\s"''])app\.py(?:[\s"'']|$)' })
if($panels.Count -ne 2 -or @($panels | Where-Object SessionId -ne 2).Count -ne 0){throw 'panel_process_topology_unexpected'}
$parent=@($panels | Where-Object { $_.ExecutablePath -eq 'C:\xiaoqian\app\wechat\.venv\Scripts\pythonw.exe' })
if($parent.Count -ne 1 -or @($panels | Where-Object { $_.ParentProcessId -eq $parent[0].ProcessId }).Count -ne 1){throw 'panel_parent_child_mismatch'}
foreach($process in $panels){Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue}
Start-Sleep -Seconds 2
if(@(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -match '(?i)(?:^|[\\/\s"''])app\.py(?:[\s"'']|$)' }).Count){throw 'panel_still_running'}
New-Item -ItemType Directory -Path $backup | Out-Null
$codeBackup=Join-Path $backup 'app';New-Item -ItemType Directory -Path $codeBackup | Out-Null
foreach($item in $items){Copy-Item -LiteralPath (Join-Path $app $item.file) -Destination (Join-Path $codeBackup $item.file)}
Copy-Item -LiteralPath (Join-Path $data 'settings.json') -Destination (Join-Path $backup 'settings.json')
foreach($kind in @('history','memory','senders')){
    $dir=Join-Path $data $kind
    if(Test-Path -LiteralPath $dir){Copy-Item -LiteralPath $dir -Destination (Join-Path $backup $kind) -Recurse}
    else{New-Item -ItemType Directory -Path (Join-Path $backup $kind) | Out-Null}
}
foreach($item in $items){
    Copy-Item -LiteralPath (Join-Path $stage $item.file) -Destination (Join-Path $app $item.file) -Force
    if((Get-FileHash -LiteralPath (Join-Path $app $item.file) -Algorithm SHA256).Hash -ne $item.after){throw 'installed_hash_invalid'}
}
& 'C:\xiaoqian\app\wechat\.venv\Scripts\python.exe' -B -X utf8 'C:\xiaoqian\setup\v35-configure-vision.py'
if($LASTEXITCODE -ne 0){throw 'vision_config_failed'}
$copied=0;$skipped=0;$cursorCopied=$false;$cursorConflict=$false
$ordered=@($mig.files | Sort-Object @{Expression={if($_.filename -like '*.learned'){1}else{0}}})
foreach($entry in $ordered){
    $dir=Join-Path $data $entry.kind
    if(!(Test-Path -LiteralPath $dir)){New-Item -ItemType Directory -Path $dir | Out-Null}
    $destination=Join-Path $dir $entry.filename
    if(Test-Path -LiteralPath $destination){$skipped++;continue}
    if($entry.reset_cursor -eq $true){
        $historyName=[IO.Path]::ChangeExtension($entry.filename,'.json')
        $existingHistory=Join-Path $dir $historyName
        $incomingHistory=Join-Path (Join-Path $incoming 'history') $historyName
        if(!(Test-Path -LiteralPath $existingHistory) -or (Get-FileHash -LiteralPath $existingHistory -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $incomingHistory -Algorithm SHA256).Hash){$skipped++;$cursorConflict=$true;continue}
    }
    Copy-Item -LiteralPath (Join-Path (Join-Path $incoming $entry.kind) $entry.filename) -Destination $destination
    if((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ne $entry.sha256){throw 'migration_copy_hash_invalid'}
    $copied++
    if($entry.reset_cursor -eq $true){$cursorCopied=$true}
}
Write-Output ('v35_files_verified=True;panel_stopped=True;migration_copied={0};migration_skipped={1};cursor_reset_copied={2};cursor_conflict={3}' -f $copied,$skipped,$cursorCopied,$cursorConflict)
