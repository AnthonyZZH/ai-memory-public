$ErrorActionPreference='Stop'
$app='C:\xiaoqian\app\wechat'
$files=@('app.py','runner.py','social_brain.py','settings.py','owner_relay.py')
foreach ($name in $files) {
    $p=Join-Path $app $name
    if (Test-Path -LiteralPath $p) { Write-Output ($name + '=' + (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash) }
    else { Write-Output ($name + '=missing') }
}
$panels=@(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -match '(?i)(?:^|[\\/\s"''])app\.py(?:[\s"'']|$)' })
Write-Output ('panel_count={0};session2_count={1}' -f $panels.Count,@($panels | Where-Object SessionId -eq 2).Count)
$cfg=Get-Content -LiteralPath 'C:\xiaoqian\data\wechat\settings.json' -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Output ('thinking_explicit_true={0}' -f ($cfg.thinking -eq $true))
