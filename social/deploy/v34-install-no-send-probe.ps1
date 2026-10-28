$ErrorActionPreference='Stop'
$old='C:\xiaoqian\setup\v33-wechat-no-send.py'
$new='C:\xiaoqian\setup\v34-wechat-no-send.py'
$bak='C:\xiaoqian\setup\v33-wechat-no-send-before-v34.py'
if ((Get-FileHash -LiteralPath $old -Algorithm SHA256).Hash -ne '829475970620DEDA5990A91FCB7A0D848499044EAAFD17D8FE3F515C62C94822') { throw 'existing_test_hash_mismatch' }
if ((Get-FileHash -LiteralPath $new -Algorithm SHA256).Hash -ne '0F24AD1546D60E461334B67049633485DD87465904BDD2E6C0068501C5A5D841') { throw 'new_test_hash_mismatch' }
if (Test-Path -LiteralPath $bak) { throw 'test_backup_exists' }
Copy-Item -LiteralPath $old -Destination $bak
Copy-Item -LiteralPath $new -Destination $old -Force
if ((Get-FileHash -LiteralPath $old -Algorithm SHA256).Hash -ne '0F24AD1546D60E461334B67049633485DD87465904BDD2E6C0068501C5A5D841') { throw 'test_install_hash_mismatch' }
Write-Output 'no_send_probe_installed_verified'
