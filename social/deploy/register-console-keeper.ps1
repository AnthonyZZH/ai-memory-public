# Registers Xiaoqian-ConsoleKeeper: on RDP session disconnect (LocalSessionManager
# event 24) run console-keeper.ps1 as SYSTEM.
$ErrorActionPreference = 'Stop'
$script = 'C:\xiaoqian\setup\console-keeper.ps1'
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Move the disconnected administrator session back to the console so WeChat keeps rendering.</Description></RegistrationInfo>
  <Triggers>
    <EventTrigger>
      <Enabled>true</Enabled>
      <Subscription>&lt;QueryList&gt;&lt;Query Id="0" Path="Microsoft-Windows-TerminalServices-LocalSessionManager/Operational"&gt;&lt;Select Path="Microsoft-Windows-TerminalServices-LocalSessionManager/Operational"&gt;*[System[(EventID=24)]]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;</Subscription>
    </EventTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT2M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>powershell.exe</Command><Arguments>-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$script"</Arguments></Exec>
  </Actions>
</Task>
"@
Register-ScheduledTask -TaskName 'Xiaoqian-ConsoleKeeper' -Xml $xml -Force | Out-Null
Get-ScheduledTask -TaskName 'Xiaoqian-ConsoleKeeper' | Select-Object TaskName, State | Format-Table -AutoSize | Out-String
