$ErrorActionPreference='Stop'
Get-Process -Name QQ,WeChat,NapCatWinBootMain,node,python -ErrorAction SilentlyContinue | Select-Object ProcessName,Id,SessionId,Path | Format-Table -AutoSize
$paths=@('C:\xiaoqian\app\napcat\config','C:\xiaoqian\data\qq','C:\xiaoqian\app\dsh','C:\xiaoqian\data\wechat')
foreach ($path in $paths) { Get-ChildItem -Force -LiteralPath $path -ErrorAction Stop | Select-Object @{n='Parent';e={$path}},Name,Mode | Format-Table -AutoSize }
