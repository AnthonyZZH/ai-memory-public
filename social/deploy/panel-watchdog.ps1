# Every few minutes: if the WeChat panel is not running, start it (it begins replying on its own).
$log = 'C:\xiaoqian\data\ops\panel-watchdog.log'
$alive = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | Where-Object { $_.CommandLine -like '*app.py*' -or $_.CommandLine -like '*run_panel*' -or $_.CommandLine -like '*appdiag*' }
if ($alive) { exit 0 }
if (-not (Get-Process Weixin -ErrorAction SilentlyContinue)) { Add-Content $log ("{0} skip: WeChat not running" -f (Get-Date -Format s)); exit 0 }
Start-Process -FilePath 'C:\xiaoqian\app\wechat\.venv\Scripts\pythonw.exe' -ArgumentList '-X','utf8','C:\xiaoqian\app\run_panel.py' -WorkingDirectory 'C:\xiaoqian\app\wechat'
Add-Content $log ("{0} panel restarted" -f (Get-Date -Format s))
