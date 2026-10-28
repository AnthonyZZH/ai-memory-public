[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
# Read-only checks; intentionally does not inspect machine environment variables.
$os=Get-CimInstance Win32_OperatingSystem
$disk=Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
[pscustomobject]@{ OS=$os.Caption; Version=$os.Version; CFreeGiB=[math]::Round($disk.FreeSpace / 1GB,2); PowerShell=$PSVersionTable.PSVersion.ToString() } | Format-List
foreach ($name in @('python','node','git','npm')) {
    $command=Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $command) { Write-Output "$name : MISSING"; continue }
    Write-Output "$name : $($command.Source)"
    & $command.Source --version
    if ($LASTEXITCODE -ne 0) { throw "version_check_failed: $name" }
}
foreach ($path in @('C:\xiaoqian\app\wechat','C:\xiaoqian\data\wechat','C:\xiaoqian\app\napcat','C:\xiaoqian\data\qq')) {
    [pscustomobject]@{ Path=$path; Exists=(Test-Path -LiteralPath $path) }
}
