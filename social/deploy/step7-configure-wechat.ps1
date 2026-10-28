$ErrorActionPreference='Stop'
$path='C:\xiaoqian\data\wechat\xq-wechat-chats.json'
& icacls.exe $path /inheritance:r /grant:r '*S-1-5-32-544:(F)' '*S-1-5-18:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'whitelist_acl_failed' }
& 'C:\Program Files\Python312\python.exe' -B -X utf8 'C:\xiaoqian\setup\step7-configure-wechat.py'
if ($LASTEXITCODE -ne 0) { throw 'wechat_configuration_failed' }
