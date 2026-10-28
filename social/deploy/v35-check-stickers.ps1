$ErrorActionPreference='Stop'
& 'C:\xiaoqian\app\wechat\.venv\Scripts\python.exe' -B -X utf8 'C:\xiaoqian\setup\v35-check-stickers.py'
if ($LASTEXITCODE -ne 0) { throw 'sticker_index_check_failed' }
