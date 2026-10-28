[CmdletBinding()]
param([Parameter(Mandatory=$true)][ValidateRange(1,65535)][int]$SessionId)
$ErrorActionPreference='Stop'
# Run only after the owner decides to disconnect RDP; requires elevation.
# Verify the session belongs to the expected account immediately before use.
& query.exe session $SessionId
if ($LASTEXITCODE -ne 0) { throw 'session_query_failed' }
Write-Output 'Review session ownership before manually running: tscon.exe <SessionId> /dest:console'
# Intentionally no tscon invocation: validation and handoff are separate.
