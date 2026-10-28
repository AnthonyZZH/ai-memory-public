$ErrorActionPreference='Stop'
$venv='C:\xiaoqian\app\wechat\.venv'
if (Test-Path -LiteralPath $venv) { throw 'wechat_venv_exists' }
& 'C:\Program Files\Python312\python.exe' -m venv $venv
if ($LASTEXITCODE -ne 0) { throw 'wechat_venv_create_failed' }
$python=Join-Path $venv 'Scripts\python.exe'
& $python -m pip install --disable-pip-version-check -r 'C:\xiaoqian\app\wechat\requirements.txt'
if ($LASTEXITCODE -ne 0) { throw 'wechat_dependencies_install_failed' }
& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'wechat_pip_check_failed' }
Write-Output 'wechat_dependencies_installed_and_pip_checked'
