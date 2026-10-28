$ErrorActionPreference='Stop'
$names=@('ss.xingzhige.com','secret-service.bietiaop.com')
$hostsPath=Join-Path $env:SystemRoot 'System32\drivers\etc\hosts'
$backup='C:\xiaoqian\setup\hosts.before-v32'
$rule='Xiaoqian-V32-block-third-party-rkey-sign'
if (Test-Path -LiteralPath $backup) { throw 'hosts_backup_exists' }
if (Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue) { throw 'firewall_rule_exists' }
$old=[IO.File]::ReadAllText($hostsPath)
if ($old -match '(?im)^\s*[^#\r\n]+\s+(ss\.xingzhige\.com|secret-service\.bietiaop\.com)(\s|$)') { throw 'hosts_existing_entry_requires_review' }
$addresses=@('106.55.0.102')
foreach ($name in $names) {
    try { $results=@([Net.Dns]::GetHostAddresses($name)) } catch { throw "dns_lookup_failed:$name" }
    if ($results.Count -eq 0) { throw "dns_no_addresses:$name" }
    foreach ($address in $results) { $addresses += $address.IPAddressToString }
}
$addresses=@($addresses | Sort-Object -Unique)
Copy-Item -LiteralPath $hostsPath -Destination $backup
New-NetFirewallRule -DisplayName $rule -Direction Outbound -Action Block -Enabled True -RemoteAddress $addresses -Profile Any | Out-Null
$append="`r`n# Xiaoqian V3.2 block third-party rkey and signing`r`n0.0.0.0 ss.xingzhige.com`r`n:: ss.xingzhige.com`r`n0.0.0.0 secret-service.bietiaop.com`r`n:: secret-service.bietiaop.com`r`n"
$stream=[IO.File]::Open($hostsPath,[IO.FileMode]::Append,[IO.FileAccess]::Write,[IO.FileShare]::Read)
try { $bytes=[Text.Encoding]::ASCII.GetBytes($append); $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
& ipconfig.exe /flushdns | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'dns_flush_failed' }
$ruleObj=Get-NetFirewallRule -DisplayName $rule
$filter=$ruleObj | Get-NetFirewallAddressFilter
if ($ruleObj.Direction -ne 'Outbound' -or $ruleObj.Action -ne 'Block' -or $ruleObj.Enabled -ne 'True') { throw 'firewall_rule_verification_failed' }
& (Join-Path $PSScriptRoot 'verify-hosts.ps1')
[pscustomobject]@{ Status='rules_created_hosts_resolve_to_unspecified'; FirewallRemoteAddresses=($filter.RemoteAddress -join ','); HostsBackup=$backup }
