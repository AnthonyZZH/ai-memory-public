$ErrorActionPreference='Stop'
& 'C:\xiaoqian\app\wechat\.venv\Scripts\python.exe' -B -X utf8 'C:\xiaoqian\setup\v35-whitelist-fingerprint.py'
if ($LASTEXITCODE -ne 0) { throw 'whitelist_fingerprint_failed' }
