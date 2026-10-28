"""Enable approved image flags without printing or exposing configuration."""
import json, os, sys
from pathlib import Path
p=Path(r'C:\xiaoqian\data\wechat\settings.json')
try:
    before=json.loads(p.read_text(encoding='utf-8-sig'))
    expected={k:v for k,v in before.items() if k not in ('describe_images','collect_stickers')}
    before['describe_images']=True;before['collect_stickers']=True
    tmp=p.with_name('settings.v35.tmp')
    with tmp.open('x',encoding='utf-8',newline='\n') as f: json.dump(before,f,ensure_ascii=False,indent=2)
    os.replace(tmp,p)
    after=json.loads(p.read_text(encoding='utf-8-sig'))
    assert after['describe_images'] is True and after['collect_stickers'] is True
    assert {k:v for k,v in after.items() if k not in ('describe_images','collect_stickers')}==expected
    print('vision_flags_enabled_config_preserved')
except Exception:
    print('vision_config_failed_redacted',file=sys.stderr);sys.exit(1)
