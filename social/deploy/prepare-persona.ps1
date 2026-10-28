param([Parameter(Mandatory=$true)][string]$OutputFile)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (Test-Path -LiteralPath $OutputFile) { throw 'Output already exists.' }
$python = Join-Path $root 'tools\xq-engine\Scripts\python.exe'
$loader = Join-Path $root 'scripts\persona_loader.py'
$env:PYTHONIOENCODING = 'utf-8'
$bytes = & $python -B $loader --target social | Out-String
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($bytes)) { throw 'Persona generation failed.' }
[System.IO.File]::WriteAllText($OutputFile, $bytes, (New-Object System.Text.UTF8Encoding($false)))
Get-FileHash -Algorithm SHA256 -LiteralPath $OutputFile | Select-Object Algorithm, Hash
