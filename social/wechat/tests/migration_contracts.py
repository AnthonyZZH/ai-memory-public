"""Synthetic staging validates whitelisting, collisions, and private reports."""
import argparse, json, subprocess, sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source-code',type=Path,required=True);p.add_argument('--tool',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
a=p.parse_args();a.work.mkdir(parents=True,exist_ok=False);source=a.work/'source';source.mkdir()
for kind in ('memory','history','senders'): (source/kind).mkdir()
chats={'synthetic group':{'mode':'group'},'outside':{'mode':'private'},'a b':{'mode':'private'},'a_b':{'mode':'private'}}
(source/'settings.json').write_text(json.dumps({'chats':chats}),encoding='utf-8')
whitelist=a.work/'whitelist.json';whitelist.write_text(json.dumps({'chats':{'synthetic group':{'mode':'group'},'a b':{'mode':'private'}}}),encoding='utf-8')
history=[{'role':'user','text':'PRIVATE_SENTINEL'}]
for name in ('synthetic_group','outside','a_b'):(source/'history'/(name+'.json')).write_text(json.dumps(history),encoding='utf-8')
(source/'memory'/'synthetic_group.json').write_text(json.dumps({'people':{},'jargon':{},'style':''}),encoding='utf-8')
(source/'senders'/'synthetic_group.json').write_text('[]',encoding='utf-8')
(source/'memory'/'backups').mkdir();(source/'memory'/'backups'/'old.json').write_text('{}',encoding='utf-8')
out=a.work/'out'
r=subprocess.run([sys.executable,'-B','-X','utf8',str(a.tool),'--source',str(source),'--whitelist',str(whitelist),'--patched-source',str(a.source_code),'--out',str(out)],capture_output=True,text=True,encoding='utf-8')
assert r.returncode==0,(r.returncode,r.stdout,r.stderr)
report=json.loads(r.stdout); counts=report['counts']
assert counts['migrated_memory']==counts['migrated_history']==counts['migrated_senders']==1
assert counts['skipped_not_whitelisted']==1 and counts['skipped_unmapped_or_ambiguous']==1 and counts['skipped_nested_backups']==1
assert 'PRIVATE_SENTINEL' not in r.stdout and 'synthetic group' not in r.stdout
assert 'PRIVATE_SENTINEL' not in (out/'manifest.json').read_text(encoding='utf-8')
print('migration_whitelist_collision_and_redaction_passed')
