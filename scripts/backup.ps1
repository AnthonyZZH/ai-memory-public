# 她的图书馆 本地备份:git 提交 + 打包到 backups。无远程上传,不删除任何文件。
# 每个本地自然日只备份一次:当天已有成功的 ZIP 则跳过。
# 用法: powershell -File E:\AI-Memory\scripts\backup.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$now = Get-Date
$day = $now.ToString('yyyyMMdd')
$stamp = $now.ToString('yyyyMMdd-HHmmss')
$backups = Join-Path $root 'backups'
New-Item -ItemType Directory -Force $backups | Out-Null

# 0. 当天已有成功备份则跳过。ZIP 先写成 .tmp 再改名,所以 *.zip 必为完整文件。
$existing = Get-ChildItem -LiteralPath $backups -Filter "AI-Memory-$day-*.zip" -File |
    Where-Object { $_.Length -gt 0 } | Select-Object -First 1
if ($existing) {
    Write-Output "skip: 今天已有备份 $($existing.FullName)"
    return
}

# 1. git 提交(只在有变更时;.gitignore 已排除 backups、cache、bin、tools 和密钥)
git add -A
if ($LASTEXITCODE -ne 0) { throw "git add 失败,退出码 $LASTEXITCODE。" }

git diff --cached --quiet
$diffCode = $LASTEXITCODE
if ($diffCode -gt 1) { throw "git diff --cached 失败,退出码 $diffCode。" }
if ($diffCode -eq 1) {
    git -c user.name='AI-Memory Backup' -c user.email='backup@localhost' commit -m "backup $stamp"
    if ($LASTEXITCODE -ne 0) { throw "git commit 失败,退出码 $LASTEXITCODE。" }
    Write-Output "git: committed backup $stamp"
} else {
    Write-Output 'git: no changes to commit'
}

# 2. 打包:git archive 只含已跟踪文件,因此遵守 .gitignore。
#    不含 backups(不会归档自己)、cache、bin、tools、密钥、*.env,也不含 .git。
$ErrorActionPreference = 'Continue'   # Windows PowerShell 5.1 下 2>$null 会把 stderr 变成终止错误
git rev-parse --verify HEAD 2>$null | Out-Null
$headCode = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
if ($headCode -ne 0) { throw '仓库还没有任何提交,无法打包。' }

$zip = Join-Path $backups "AI-Memory-$stamp.zip"
$tmp = "$zip.tmp"
if ((Test-Path -LiteralPath $zip) -or (Test-Path -LiteralPath $tmp)) { throw "目标已存在,不覆盖: $zip" }
git archive --format=zip -o $tmp HEAD
if ($LASTEXITCODE -ne 0) { throw "git archive 失败,退出码 $LASTEXITCODE;残留 $tmp 未删除,请手动检查。" }
Move-Item -LiteralPath $tmp -Destination $zip
Write-Output "zip: $zip"
