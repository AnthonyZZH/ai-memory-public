"""Headless local-only main MCP task. Does not inherit credentials/provider settings."""
import os,subprocess,sys
from pathlib import Path
ROOT=Path(r'C:\AI-Library\main')
allowed={'SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT','TEMP','TMP','USERPROFILE','APPDATA','LOCALAPPDATA','HOMEDRIVE','HOMEPATH','PROGRAMDATA'}
env={k:v for k,v in os.environ.items() if k.upper() in allowed}
env.update({
    'BASIC_MEMORY_CONFIG_DIR':str(ROOT/'state'),
    'BASIC_MEMORY_HOME':str(ROOT/'vault'),
    'BASIC_MEMORY_NO_PROMOS':'1','BASIC_MEMORY_LOG_LEVEL':'WARNING',
    'BASIC_MEMORY_DEFAULT_SEARCH_TYPE':'text',
    'BASIC_MEMORY_RERANKER_ENABLED':'false',
    'BASIC_MEMORY_LOGFIRE_ENABLED':'false',
    'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1','DO_NOT_TRACK':'1',
    'FASTEMBED_CACHE_DIR':str(ROOT/'cache'),'PYTHONIOENCODING':'utf-8',
})
args=[str(ROOT/'venv'/'Scripts'/'basic-memory.exe'),'mcp','--transport','streamable-http','--host','127.0.0.1','--port','8767','--path','/mcp','--project','main']
(ROOT/'logs').mkdir(exist_ok=True)
with (ROOT/'logs'/'main-mcp.log').open('ab',buffering=0) as log:
    result=subprocess.run(args,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
sys.exit(result.returncode)
