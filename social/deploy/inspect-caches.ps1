$ErrorActionPreference='Stop'
$roots=@((Join-Path $env:USERPROFILE 'Documents\WeChat Files'),(Join-Path $env:USERPROFILE 'Documents\Tencent Files'),(Join-Path $env:APPDATA 'Tencent'),(Join-Path $env:LOCALAPPDATA 'Tencent'))
foreach ($root in $roots) {
    if (-not (Test-Path -LiteralPath $root)) { continue }
    Write-Output "ROOT $root"
    Get-ChildItem -LiteralPath $root -Directory -Force | ForEach-Object {
        $name=if ($_.Name -match '^\d{5,}$|^wxid_') {'<account>'} else {$_.Name}
        Write-Output "  DIR $name"
        Get-ChildItem -LiteralPath $_.FullName -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {
            $child=if ($_.Name -match '^\d{5,}$|^wxid_') {'<account>'} else {$_.Name}
            Write-Output "    DIR $child"
        }
    }
}
