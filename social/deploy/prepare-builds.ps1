param([Parameter(Mandatory=$true)][string]$OutputRoot)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$python = Join-Path $root 'tools\xq-engine\Scripts\python.exe'
if (Test-Path -LiteralPath $OutputRoot) { throw 'OutputRoot already exists; choose a new path.' }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
& $python -B (Join-Path $root 'social\build\fetch-and-patch.py') --source-root 'E:\Codex Development\tmp\v3.0' --out (Join-Path $OutputRoot 'qq')
if ($LASTEXITCODE -ne 0) { throw 'QQ build failed; output preserved.' }
& $python -B (Join-Path $root 'social\wechat\build\fetch-and-patch.py') --source-root 'E:\Projects' --out (Join-Path $OutputRoot 'wechat')
if ($LASTEXITCODE -ne 0) { throw 'WeChat build failed; output preserved.' }
Write-Output 'Pinned source trees verified; no installation or network connection performed.'
