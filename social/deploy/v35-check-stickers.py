"""Inspect index counts only; never print identifiers or descriptions."""
import json
from pathlib import Path
try:
    root=Path(r'C:\xiaoqian\data\wechat\stickers')
    data=json.loads((root/'index.json').read_text(encoding='utf-8-sig'))
    if not isinstance(data,dict): raise ValueError()
    n=len(data)
    empty=sum(not isinstance(v,dict) or not isinstance(v.get('desc'),str) or not v['desc'].strip() for v in data.values())
    replaced=sum(isinstance(v,dict) and isinstance(v.get('desc'),str) and '\ufffd' in v['desc'] for v in data.values())
    missing=sum(not isinstance(v,dict) or not isinstance(v.get('file'),str) or Path(v['file']).name != v['file'] or not (root/v['file']).is_file() for v in data.values())
    print(f'index_entries={n};empty_descriptions={empty};replacement_descriptions={replaced};missing_files={missing}')
except Exception:
    print('sticker_index_invalid')
    raise SystemExit(1)
