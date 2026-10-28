"""Create an ACL-restricted migration package and reset one stale cursor."""
import hashlib, importlib.util, json, shutil, sys, time, zipfile
from pathlib import Path

SOURCE=Path(r'E:\Codex Development\tmp\v35-migration-staged-final')
DEST=Path(r'E:\Codex Development\tmp\v35-migration-transfer-v2')
EXPECTED='abf7bf7473b8cfa47f96e362a98c960016eea3c2e0d49656f1c3d493c64532a7'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    manifest_path=SOURCE/'manifest.json'
    if sha(manifest_path)!=EXPECTED: raise ValueError()
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    if len(manifest['files'])!=22: raise ValueError()
    spec=importlib.util.spec_from_file_location('migration',Path(__file__).with_name('migrate_legacy_data.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.secure_directory(DEST)
    staged=DEST/'staged';staged.mkdir()
    for item in manifest['files']:
        kind=item['kind'];name=item['name_hash'];ext=item['extension']
        if kind not in ('memory','history','senders') or len(name)!=64 or any(c not in '0123456789abcdef' for c in name) or ext not in ('.json','.learned'): raise ValueError()
        source=SOURCE/kind/(name+ext);target=staged/kind/(name+ext)
        if sha(source)!=item['sha256']: raise ValueError()
        target.parent.mkdir(exist_ok=True);shutil.copyfile(source,target)
    reset=0;reset_name=None
    for marker in (staged/'history').glob('*.learned'):
        history=marker.with_suffix('.json')
        if not history.exists():raise ValueError()
        item=json.loads(marker.read_text(encoding='utf-8'));rows=json.loads(history.read_text(encoding='utf-8'))
        if not any(row.get('role')==item['last'][0] and ''.join(row.get('text','').split())==item['last'][1] for row in rows):
            if not rows or rows[-1].get('role') not in ('user','assistant') or not isinstance(rows[-1].get('text'),str):raise ValueError()
            item={'last':[rows[-1]['role'],''.join(rows[-1]['text'].split())],'at':time.time()}
            marker.write_text(json.dumps(item,ensure_ascii=False),encoding='utf-8');reset+=1;reset_name=marker.name
    if reset!=1:raise ValueError()
    items=[]
    for item in manifest['files']:
        p=staged/item['kind']/(item['name_hash']+item['extension'])
        items.append({'kind':item['kind'],'filename':p.name,'sha256':sha(p),'reset_cursor':p.name==reset_name and item['kind']=='history'})
    archive=DEST/'migration.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for item in items:z.write(staged/item['kind']/item['filename'],item['kind']+'/'+item['filename'])
        z.writestr('manifest.json',json.dumps({'files':items},ensure_ascii=True))
    print('files='+str(len(items))+';cursor_reset='+str(reset)+';archive_sha256='+sha(archive))
if __name__=='__main__':
    try:main()
    except Exception:
        print('migration_package_failed',file=sys.stderr);sys.exit(1)
