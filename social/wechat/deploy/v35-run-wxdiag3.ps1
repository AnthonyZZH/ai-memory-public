$ErrorActionPreference='Stop'
$original='C:\xiaoqian\setup\wxdiag3.py';$candidate='C:\xiaoqian\setup\v35-wxdiag3.py';$backup='C:\xiaoqian\setup\wxdiag3-before-v35.py'
$diag='C:\xiaoqian\data\wechat\v33-audit\diag.json';$diagBackup='C:\xiaoqian\data\wechat\v33-audit\diag-before-v35.json'
if((Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash -ne '3AAC51A7E6AF7558817AEEC9F3F911CEF568DB557B16C53A339EC8AA3EF35B90'){throw 'diag_script_changed'}
if((Test-Path -LiteralPath $backup) -or (Test-Path -LiteralPath $diagBackup) -or (Get-ScheduledTask -TaskName 'XiaoqianWxDiag' -ErrorAction SilentlyContinue)){throw 'diag_backup_or_task_exists'}
Copy-Item -LiteralPath $original -Destination $backup
if(Test-Path -LiteralPath $diag){Copy-Item -LiteralPath $diag -Destination $diagBackup}
try {
    Copy-Item -LiteralPath $candidate -Destination $original -Force
    $discard=@(& 'C:\xiaoqian\setup\wxdiag3.ps1')
    if(!(Test-Path -LiteralPath $diag)){throw 'diag_output_missing'}
    $result=Get-Content -LiteralPath $diag -Raw -Encoding UTF8 | ConvertFrom-Json
    Write-Output ('opened_owner={0};send_blocked={1};read_whitelisted_chat={2};thinking_disabled={3};group_digest_nonempty={4};memory_retrieved={5}' -f $result.opened_owner,$result.send_blocked,$result.read_whitelisted_chat,$result.thinking_disabled,$result.group_digest_nonempty,$result.memory_retrieved)
    if(!$result.opened_owner -or !$result.send_blocked -or !$result.read_whitelisted_chat -or !$result.thinking_disabled){throw 'v35_no_send_acceptance_failed'}
} finally {Copy-Item -LiteralPath $backup -Destination $original -Force}
