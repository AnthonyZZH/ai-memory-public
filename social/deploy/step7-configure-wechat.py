import json
from pathlib import Path
import sys

try:
    data=Path(r'C:\xiaoqian\data\wechat')
    source=data/'xq-wechat-chats.json'
    persona=Path(r'C:\xiaoqian\data\shared\persona-social.txt').read_text(encoding='utf-8')
    doc=json.loads(source.read_text(encoding='utf-8-sig'))
    keys=('chats','owner','aliases','blocked','initiative_private_chats')
    if not isinstance(doc,dict) or any(k not in doc for k in keys): raise ValueError()
    if not isinstance(doc['chats'],dict) or not isinstance(doc['owner'],str): raise ValueError()
    if any(not isinstance(doc[k],list) for k in keys[2:]): raise ValueError()
    if not persona.strip() or len(persona)>12000: raise ValueError()
    settings=data/'settings.json'; personadir=data/'personas'; dest=personadir/'小千.json'
    if settings.exists() or dest.exists(): raise FileExistsError()
    conf={k:doc[k] for k in keys}
    conf.update({'base_url':'https://api.deepseek.com','api_key_env':'XQ_DEEPSEEK_API_KEY','model':{'key':'deepseek-api','identifier':'deepseek-flash'},'persona':'小千','agents_enabled':False,'web_search':False,'draw_for_members':False})
    personadir.mkdir(exist_ok=False)
    with dest.open('x',encoding='utf-8',newline='\n') as f: json.dump({'name':'小千','prompt':persona,'temperature':0.85},f,ensure_ascii=False,indent=2)
    with settings.open('x',encoding='utf-8',newline='\n') as f: json.dump(conf,f,ensure_ascii=False,indent=2)
    print('wechat_settings_and_persona_written_sensitive_values_redacted')
except Exception:
    print('wechat_configuration_failed_sensitive_values_redacted',file=sys.stderr)
    sys.exit(1)
