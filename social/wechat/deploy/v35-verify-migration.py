"""Report only aggregate integrity and cursor booleans."""
import hashlib,json,sys
from pathlib import Path
try:
    root=Path(r'C:\xiaoqian\data\wechat');stage=root/'v35-incoming'
    entries=json.loads((stage/'manifest.json').read_text(encoding='utf-8'))['files']
    valid=0;missing=0
    for item in entries:
        p=root/item['kind']/item['filename']
        if not p.is_file():missing+=1;continue
        if hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']:valid+=1
    reset=[x for x in entries if x.get('reset_cursor') is True]
    if len(reset)!=1:raise ValueError()
    marker=root/'history'/reset[0]['filename'];history=marker.with_suffix('.json')
    mark=json.loads(marker.read_text(encoding='utf-8'));rows=json.loads(history.read_text(encoding='utf-8'))
    cursor=bool(rows) and mark.get('last')==[rows[-1].get('role'),''.join(rows[-1].get('text','').split())]
    config=json.loads((root/'settings.json').read_text(encoding='utf-8-sig'))
    print('files_expected='+str(len(entries))+';files_hash_match='+str(valid)+';files_missing='+str(missing)
          +';cursor_at_end='+str(cursor)+';image_enabled='+str(config.get('describe_images') is True)
          +';collection_enabled='+str(config.get('collect_stickers') is True))
    if valid!=len(entries) or missing or not cursor: raise ValueError()
except Exception:
    print('migration_verify_failed',file=sys.stderr);sys.exit(1)
