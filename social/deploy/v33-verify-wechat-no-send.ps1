$ErrorActionPreference = 'Stop'
& 'C:\xiaoqian\app\wechat\.venv\Scripts\python.exe' -B -X utf8 'C:\xiaoqian\setup\no_send_entry.py' --source 'C:\xiaoqian\app\wechat' --entry 'C:\xiaoqian\setup\v33-wechat-no-send.py' --work 'C:\xiaoqian\setup\v33-no-send-fake-test'
if ($LASTEXITCODE -ne 0) { throw 'wechat_no_send_fake_test_failed' }
& 'C:\xiaoqian\setup\v33-prepare-wechat-no-send.ps1'
