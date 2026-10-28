$ErrorActionPreference='Stop'
foreach ($p in @('C:\xiaoqian\setup\stickers.zip','C:\xiaoqian\data\wechat\stickers.zip')) {
    if (Test-Path -LiteralPath $p -PathType Leaf) {
        $item=Get-Item -LiteralPath $p
        Write-Output ('archive_bytes={0}' -f $item.Length)
    }
}
