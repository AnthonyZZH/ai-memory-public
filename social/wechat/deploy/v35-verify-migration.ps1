$ErrorActionPreference='Stop'
& 'C:\xiaoqian\app\wechat\.venv\Scripts\python.exe' -B -X utf8 'C:\xiaoqian\setup\v35-verify-migration.py'
if($LASTEXITCODE -ne 0){throw 'migration_verify_failed'}
