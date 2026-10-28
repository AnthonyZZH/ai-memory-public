[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
# These directories must be verified against the installed versions before registration.
$policies = @(
    @{ Path = 'C:\xiaoqian\data\qq\media-cache'; Days = 7 },
    @{ Path = 'C:\xiaoqian\data\wechat\media-cache'; Days = 7 },
    @{ Path = 'C:\xiaoqian\logs'; Days = 14 }
)
function Assert-NoReparse([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -Force -LiteralPath $current
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'reparse_point_rejected' }
        }
        $parent = [IO.Directory]::GetParent($current)
        if ($null -eq $parent) { break }
        $current = $parent.FullName
    }
}
function Scan-Directory([string]$Root, [datetime]$Cutoff) {
    Assert-NoReparse $Root
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { return }
    $pending = New-Object 'System.Collections.Generic.Stack[string]'
    $pending.Push($Root)
    while ($pending.Count -gt 0) {
        $dir = $pending.Pop()
        Assert-NoReparse $dir
        foreach ($item in Get-ChildItem -Force -LiteralPath $dir) {
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'reparse_point_rejected' }
            if ($item.PSIsContainer) { $pending.Push($item.FullName); continue }
            if ($item.LastWriteTimeUtc -lt $Cutoff) {
                Assert-NoReparse $item.FullName
                if ($Apply) { Remove-Item -LiteralPath $item.FullName -Force -ErrorAction Stop }
                [pscustomobject]@{ Policy = $Root; Action = $(if ($Apply) {'deleted'} else {'would-delete'}); Bytes = $item.Length }
            }
        }
    }
}
foreach ($policy in $policies) { Scan-Directory $policy.Path ([DateTime]::UtcNow.AddDays(-$policy.Days)) }
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
if ($null -eq $disk) { throw 'disk_query_failed' }
if ($disk.FreeSpace -lt 5GB) {
    $alerts = 'C:\xiaoqian\alerts'
    Assert-NoReparse $alerts
    if ($Apply) {
        New-Item -ItemType Directory -Force -Path $alerts | Out-Null
        Assert-NoReparse $alerts
        [IO.File]::WriteAllText((Join-Path $alerts 'low-disk.txt'), "Low disk space on C: at $([DateTime]::UtcNow.ToString('o')) UTC`r`n")
    }
    Write-Output 'low_disk_alert'
}
