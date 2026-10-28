$ErrorActionPreference='Stop'
$p='C:\xiaoqian\data\wechat\stickers'
if (!(Test-Path -LiteralPath $p -PathType Container)) { Write-Output 'sticker_dir_missing'; exit 2 }
$files=@(Get-ChildItem -LiteralPath $p -File)
$images=@($files | Where-Object { $_.Extension -match '^\.(png|jpg|jpeg|gif|webp)$' })
Write-Output ('files={0};images={1};index={2}' -f $files.Count,$images.Count,(Test-Path -LiteralPath (Join-Path $p 'index.json') -PathType Leaf))
