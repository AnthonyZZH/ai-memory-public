$ErrorActionPreference='Stop'
$node='C:\Program Files\nodejs\node.exe'
& $node 'C:\xiaoqian\setup\v33-foreground-debug.cjs'
if ($LASTEXITCODE -ne 0) { throw 'foreground_debug_failed' }
