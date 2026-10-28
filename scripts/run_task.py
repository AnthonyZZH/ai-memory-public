import os,subprocess,sys,pathlib
root=pathlib.Path(r'E:\AI-Memory')
task=sys.argv[1] if len(sys.argv)==2 else ''
commands={'serve':[str(root/'bin/basic-memory.exe'),'mcp','--transport','streamable-http','--host','127.0.0.1','--port','8767','--path','/mcp','--project','main'],'serve-private':[str(root/'bin/basic-memory.exe'),'mcp','--transport','streamable-http','--host','127.0.0.1','--port','8768','--path','/mcp','--project','private'],'backup':['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(root/'scripts/backup.ps1')]}
commands['backup-private']=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(root/'scripts/backup-private.ps1')]
if task not in commands:raise SystemExit(2)
env=os.environ.copy();env.update(BASIC_MEMORY_NO_PROMOS='1',FASTEMBED_CACHE_DIR=str(root/'cache/fastembed'),HF_HUB_OFFLINE='1',TEMP=str(root/'cache/tmp'),TMP=str(root/'cache/tmp'))
if task == 'backup-private':
 # Never place child stdout/stderr (including Git filenames) in the shared log.
 try:
  result=subprocess.run(commands[task],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
  code=result.returncode
 except OSError:
  code=1
 with (root/'cache/task-backup-private.log').open('a',encoding='utf-8') as log:
  log.write(f'result_code={code}\n')
 raise SystemExit(code)
with (root/f'cache/task-{task}.log').open('ab') as log:
 result=subprocess.run(commands[task],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
raise SystemExit(result.returncode)
