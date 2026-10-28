# Local private backup. Never emit Git output or private filenames.
$ErrorActionPreference = 'Stop'
$root = 'E:\AI-Memory-private'
$resultCode = 1
function Invoke-PrivateGit {
    param([string[]]$GitArguments)
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $captured = @(& git -c safe.directory=E:/AI-Memory-private -C $root @GitArguments 2>&1)
    $code = $LASTEXITCODE
    $ErrorActionPreference = $oldPreference
    return [pscustomobject]@{ Code = $code; Output = $captured }
}
try {
    # Refuse to initialize a repository or use a parent repository implicitly.
    if (-not (Test-Path -LiteralPath (Join-Path $root '.git') -PathType Container)) { throw 'repository' }
    $check = Invoke-PrivateGit -GitArguments @('rev-parse', '--show-toplevel')
    if ($check.Code -ne 0 -or ([string]$check.Output[0]).Replace('\','/').TrimEnd('/') -ne $root.Replace('\','/')) { throw 'root' }
    $check = Invoke-PrivateGit -GitArguments @('rev-parse', '--verify', 'HEAD')
    if ($check.Code -ne 0) { throw 'initial commit required' }
    $now = Get-Date
    $day = $now.ToString('yyyyMMdd')
    $stamp = $now.ToString('yyyyMMdd-HHmmss-fff')
    $backups = Join-Path $root 'backups'
    New-Item -ItemType Directory -Force -Path $backups | Out-Null
    $existing = Get-ChildItem -LiteralPath $backups -Filter "AI-Memory-private-$day-*.zip" -File |
        Where-Object { $_.Length -gt 0 } | Select-Object -First 1
    if ($existing) {
        Write-Output 'skip: result_code=0'
        exit 0
    }
    $check = Invoke-PrivateGit -GitArguments @('add', '-A')
    if ($check.Code -ne 0) { throw 'stage' }
    $check = Invoke-PrivateGit -GitArguments @('diff', '--cached', '--quiet')
    if ($check.Code -notin @(0,1)) { throw 'diff' }
    if ($check.Code -eq 1) {
        $check = Invoke-PrivateGit -GitArguments @('-c', 'user.name=AI-Memory Backup', '-c', 'user.email=backup@localhost', 'commit', '-m', "backup $stamp")
        if ($check.Code -ne 0) { throw 'commit' }
        Write-Output 'commit_result_code=0 changed=1'
    } else {
        Write-Output 'commit_result_code=0 changed=0'
    }
    $zip = Join-Path $backups "AI-Memory-private-$stamp.zip"
    $temporary = "$zip.tmp"
    if ((Test-Path -LiteralPath $zip) -or (Test-Path -LiteralPath $temporary)) { throw 'collision' }
    $check = Invoke-PrivateGit -GitArguments @('archive', '--format=zip', '-o', $temporary, 'HEAD')
    if ($check.Code -ne 0) { throw 'archive' }
    Move-Item -LiteralPath $temporary -Destination $zip
    $resultCode = 0
} catch {
    # Retain partial archives; never expose exception text or captured Git output.
    $resultCode = 1
}
Write-Output "result_code=$resultCode"
exit $resultCode
