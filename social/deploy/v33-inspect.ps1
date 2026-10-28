$ErrorActionPreference='Stop'
Get-Process -Name QQ,WeChat,NapCatWinBootMain,node,python -ErrorAction SilentlyContinue | Select-Object ProcessName,Id,SessionId,Path | Format-Table -AutoSize
Get-NetTCPConnection -State Listen -LocalPort 3001,6099 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize
$keys=@('HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64','HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64')
foreach ($key in $keys) { if (Test-Path -LiteralPath $key) { Get-ItemProperty -LiteralPath $key | Select-Object Installed,Version,Major,Minor,Bld,Rbld | Format-List } }
