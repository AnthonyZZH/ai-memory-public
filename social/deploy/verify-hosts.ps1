$ErrorActionPreference='Stop'
foreach ($name in @('ss.xingzhige.com','secret-service.bietiaop.com')) {
    try { $resolved=@([Net.Dns]::GetHostAddresses($name) | ForEach-Object IPAddressToString) }
    catch [System.Net.Sockets.SocketException] {
        # Host-not-found / no-data indicate blocked name resolution; other DNS errors remain failures.
        if ($_.Exception.SocketErrorCode -notin @([Net.Sockets.SocketError]::HostNotFound,[Net.Sockets.SocketError]::NoData)) { throw }
        Write-Output "$name : resolution_blocked"
        continue
    }
    if ($resolved.Count -eq 0) { Write-Output "$name : resolution_blocked"; continue }
    if (@($resolved | Where-Object { $_ -notin @('0.0.0.0','::') }).Count -ne 0) { throw "unexpected_resolved_address:$name" }
    Write-Output "$name : resolution_blocked"
}
