$ErrorActionPreference='Stop'
& 'C:\Program Files\nodejs\node.exe' 'C:\xiaoqian\setup\v33-foreground-audit.cjs'
if ($LASTEXITCODE -ne 0) { throw 'foreground_audit_failed' }
