$ErrorActionPreference='Stop'
$paths=@('C:\xiaoqian\app\wechat','C:\xiaoqian\data\wechat','C:\xiaoqian\app\napcat','C:\xiaoqian\data\qq','C:\xiaoqian\data\shared')
foreach ($path in $paths) { if (Test-Path -LiteralPath $path) { throw 'target_already_exists' } }
foreach ($path in $paths) { New-Item -ItemType Directory -Path $path | Out-Null }
Write-Output 'step3_directories_created'
