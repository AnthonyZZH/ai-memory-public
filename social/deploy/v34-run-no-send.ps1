$ErrorActionPreference='Stop'
$task='XiaoqianV34NoSendOnce'; $audit='C:\xiaoqian\data\wechat\v33-audit'
if (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue) { throw 'no_send_task_exists' }
$existing=@(Get-ChildItem -LiteralPath $audit -Filter 'no-send-*.json' -File | ForEach-Object Name)
$action=New-ScheduledTaskAction -Execute 'C:\xiaoqian\app\wechat\.venv\Scripts\pythonw.exe' -Argument '-B -X utf8 C:\xiaoqian\setup\v34-no-send-launch.py' -WorkingDirectory 'C:\xiaoqian\app\wechat'
$principal=New-ScheduledTaskPrincipal -UserId 'administrator' -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $task -Action $action -Principal $principal | Out-Null
try {
    Start-ScheduledTask -TaskName $task
    $new=@()
    for($i=0;$i -lt 75;$i++){
        Start-Sleep -Seconds 2
        $new=@(Get-ChildItem -LiteralPath $audit -Filter 'no-send-*.json' -File | Where-Object { $_.Name -notin $existing })
        if($new.Count){break}
    }
    if ($new.Count -ne 1) { throw 'no_send_result_missing_or_ambiguous' }
    $r=Get-Content -LiteralPath $new[0].FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    Write-Output ('status={0};read_whitelisted_chat={1};model_returned={2};thinking_disabled={3};send_attempts={4}' -f $r.status,$r.read_whitelisted_chat,$r.model_returned,$r.thinking_disabled,@($r.send_attempts).Count)
    if ($r.status -ne 'send_blocked' -or !$r.read_whitelisted_chat -or !$r.model_returned -or !$r.thinking_disabled -or @($r.send_attempts).Count -ne 1) { throw 'no_send_acceptance_failed' }
} finally { Unregister-ScheduledTask -TaskName $task -Confirm:$false }
