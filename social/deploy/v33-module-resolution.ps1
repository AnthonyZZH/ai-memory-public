$ErrorActionPreference='Stop'
& 'C:\Program Files\nodejs\node.exe' 'C:\xiaoqian\setup\v33-module-resolution.cjs'
if ($LASTEXITCODE -ne 0) { throw 'module_resolution_failed' }
