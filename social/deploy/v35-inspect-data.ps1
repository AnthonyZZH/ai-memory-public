$ErrorActionPreference='Stop'
$root='C:\xiaoqian\data\wechat'
$acl=Get-Acl -LiteralPath $root
$allowed=@('S-1-5-32-544','S-1-5-18')
$unexpected=0
foreach($rule in $acl.Access){
    $sid=$rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
    if($sid -notin $allowed){$unexpected++}
}
Write-Output ('acl_inheritance_disabled={0};unexpected_access_entries={1}' -f $acl.AreAccessRulesProtected,$unexpected)
