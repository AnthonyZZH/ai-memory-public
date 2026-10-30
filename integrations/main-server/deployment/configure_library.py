"""Create only the new isolated main configuration after official installation."""
import os,json,importlib.metadata
from pathlib import Path
ROOT=Path(r'C:\AI-Library\main')
for key in list(os.environ):
    if key.startswith('BASIC_MEMORY_') or key.endswith('_API_KEY') or key in {'OPENAI_BASE_URL','ANTHROPIC_AUTH_TOKEN'}:os.environ.pop(key,None)
os.environ['BASIC_MEMORY_CONFIG_DIR']=str(ROOT/'state')
os.environ['BASIC_MEMORY_HOME']=str(ROOT/'vault')
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
from basic_memory.config_models import BasicMemoryConfig
from basic_memory.repository.semantic_runtime import semantic_runtime_available
assert importlib.metadata.version('basic-memory')=='0.24.1','VERSION_MISMATCH'
fields={'projects':{'main':{'path':str(ROOT/'vault'),'mode':'local'}},'default_project':'main','default_search_type':'text','reranker_enabled':False,'logfire_enabled':False,'logfire_send_to_logfire':False,'enable_posix_tools':False}
assert all(k in BasicMemoryConfig.model_fields for k in fields),'CONFIG_CONTRACT_MISMATCH'
config=BasicMemoryConfig(**fields)
assert not semantic_runtime_available(config),'SEMANTIC_RUNTIME_MUST_BE_DISABLED'
state=ROOT/'state';state.mkdir(exist_ok=True)
target=state/'config.json'
assert not target.exists(),'CONFIG_ALREADY_EXISTS'
target.write_text(json.dumps(fields,indent=2),encoding='utf-8')
print(json.dumps({'version':'0.24.1','project':'main','semantic_runtime':False,'default_search_type':'text','isolated_config':True}))
