"""Stage whitelisted legacy chat data without disclosing identities or contents."""
import argparse, csv, hashlib, importlib.util, io, json, math, os, re, subprocess, sys
from collections import Counter
from pathlib import Path

def legacy_name(name):
    return re.sub(r'[\\/:*?"<>|\s]+','_',name.strip())[:40]

def no_link(path):
    return not path.is_symlink() and not (getattr(path.lstat(),'st_file_attributes',0) & 0x400)

def secure_directory(path):
    path.mkdir(parents=True, exist_ok=False)
    if os.name == 'nt':
        data=subprocess.check_output(['whoami','/user','/fo','csv','/nh'],text=True,encoding='utf-8',errors='strict')
        sid=next(csv.reader(io.StringIO(data)))[1]
        if not re.fullmatch(r'S-1-[0-9-]+',sid): raise ValueError()
        result=subprocess.run(['icacls',str(path),'/inheritance:r','/grant:r',f'*{sid}:(OI)(CI)F','*S-1-5-18:(OI)(CI)F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if result.returncode: raise ValueError()

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--whitelist',type=Path,required=True)
    p.add_argument('--patched-source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    source=a.source.resolve();target=a.out.resolve()
    if source==target or source in target.parents or target in source.parents: raise ValueError()
    if not no_link(a.source) or not no_link(a.whitelist): raise ValueError()
    old=json.loads((source/'settings.json').read_text(encoding='utf-8-sig'))
    allowed=json.loads(a.whitelist.read_text(encoding='utf-8-sig'))['chats']
    if not isinstance(old.get('chats'),dict) or not isinstance(allowed,dict): raise ValueError()
    mapping={}
    for name,info in old['chats'].items():
        if not isinstance(name,str) or not isinstance(info,dict): raise ValueError()
        mapping.setdefault(legacy_name(name).casefold(),[]).append((name,info.get('mode')))
    spec=importlib.util.spec_from_file_location('migration_memory',a.patched_source/'memory.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    secure_directory(target)
    counts=Counter();files=[]
    for kind in ('memory','history','senders'):
        folder=source/kind
        if not folder.is_dir() or not no_link(folder): raise ValueError()
        for path in folder.rglob('*'):
            if path.is_dir():
                if not no_link(path): raise ValueError()
                continue
            counts['source_files']+=1
            if not no_link(path): raise ValueError()
            if path.parent!=folder:
                counts['skipped_nested_backups']+=1;continue
            matches=mapping.get(path.stem.casefold(),[])
            if len(matches)!=1:
                counts['skipped_unmapped_or_ambiguous']+=1;continue
            name,mode=matches[0]
            if name not in allowed or not isinstance(allowed[name],dict) or allowed[name].get('mode')!=mode or mode not in ('private','group'):
                counts['skipped_not_whitelisted']+=1;continue
            if (kind=='memory' and path.suffix!='.json') or (kind=='history' and path.suffix not in ('.json','.learned')) or (kind=='senders' and (path.suffix!='.json' or mode!='group')):
                counts['skipped_type']+=1;continue
            try:
                data=json.loads(path.read_text(encoding='utf-8-sig'))
                if kind=='memory':
                    if module.Memory.validate_edit(data)!=data: raise ValueError()
                elif kind=='history' and path.suffix=='.json':
                    if not isinstance(data,list) or any(not isinstance(x,dict) or x.get('role') not in ('user','assistant') or not isinstance(x.get('text'),str) or ('sender' in x and not isinstance(x['sender'],str)) for x in data): raise ValueError()
                elif kind=='history':
                    if not isinstance(data,dict) or not isinstance(data.get('last'),list) or len(data['last'])!=2 or data['last'][0] not in ('user','assistant') or not isinstance(data['last'][1],str) or type(data.get('at')) not in (int,float) or not math.isfinite(data['at']): raise ValueError()
                else:
                    if not isinstance(data,list) or any(not isinstance(x,dict) or not isinstance(x.get('names'),dict) or any(not isinstance(k,str) or type(n) is not int or n<0 for k,n in x.get('names',{}).items()) or not str(x.get('hash','')).isdigit() or x.get('label') is not None and not isinstance(x.get('label'),str) for x in data): raise ValueError()
            except Exception:
                counts['skipped_invalid_format']+=1;continue
            digest=hashlib.sha256((mode+'\0'+name).encode('utf-8')).hexdigest()
            dest=target/kind/(digest+path.suffix);dest.parent.mkdir(exist_ok=True)
            payload=(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
            with dest.open('xb') as stream:stream.write(payload)
            files.append({'kind':kind,'name_hash':digest,'extension':path.suffix,'sha256':hashlib.sha256(payload).hexdigest()})
            counts['migrated_'+kind]+=1
    for marker in (target/'history').glob('*.learned') if (target/'history').exists() else ():
        history=marker.with_suffix('.json')
        if not history.exists():
            counts['marker_missing_history']+=1
            continue
        item=json.loads(marker.read_text(encoding='utf-8'))
        rows=json.loads(history.read_text(encoding='utf-8'))
        if not any(row.get('role')==item['last'][0] and ''.join(row.get('text','').split())==item['last'][1] for row in rows):
            counts['marker_not_in_history']+=1
    manifest={'counts':dict(counts),'files':files}
    report=json.dumps(manifest,ensure_ascii=True,sort_keys=True,indent=2).encode('utf-8')
    (target/'manifest.json').write_bytes(report)
    print(json.dumps({'counts':dict(counts),'manifest_sha256':hashlib.sha256(report).hexdigest()},sort_keys=True))

if __name__=='__main__':
    try: main()
    except Exception:
        print('migration_failed_redacted',file=sys.stderr)
        sys.exit(1)
