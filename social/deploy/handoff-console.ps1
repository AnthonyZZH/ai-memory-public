[CmdletBinding(SupportsShouldProcess=$true,ConfirmImpact='High')]
param([Parameter(Mandatory=$true)][ValidateRange(1,65535)][int]$SessionId)
$ErrorActionPreference='Stop'
& query.exe session $SessionId
if ($LASTEXITCODE -ne 0) { throw 'session_query_failed' }
if ($PSCmdlet.ShouldProcess("session $SessionId",'Transfer to console and disconnect remote desktop')) {
    & "$env:WINDIR\System32\tscon.exe" $SessionId /dest:console
    if ($LASTEXITCODE -ne 0) { throw 'tscon_failed' }
}
