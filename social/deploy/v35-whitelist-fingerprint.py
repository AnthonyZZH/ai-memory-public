"""Print only a digest and count of current chat names and modes."""
import hashlib,json
from pathlib import Path
try:
    settings=json.loads(Path(r'C:\xiaoqian\data\wechat\settings.json').read_text(encoding='utf-8-sig'))
    chats=settings['chats']
    value=sorted((name,info.get('mode')) for name,info in chats.items())
    raw=json.dumps(value,ensure_ascii=True,separators=(',',':')).encode('ascii')
    print('chat_count='+str(len(value))+';whitelist_sha256='+hashlib.sha256(raw).hexdigest())
except Exception:
    print('whitelist_fingerprint_failed')
    raise SystemExit(1)
