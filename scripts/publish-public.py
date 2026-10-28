"""Publish public notes plus a social persona. Default: read-only planning.

Only manifest-owned files may be replaced. Revoked notes are moved OUT of the
public tree into owner-side backups, never deleted or left in a public archive.
No network or model call. Bodies, names and keys are never printed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import os
import sys
from datetime import datetime, timezone
import yaml
from persona_loader import DEFAULT_SOURCE_DIR, load_persona, render_persona

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = '.public-manifest.json'


class UniqueLoader(yaml.SafeLoader):
    """Ambiguous classification must never promote a note to public."""


def unique_mapping(loader,node,deep=False):
    result={}
    for key_node,value_node in node.value:
        key=loader.construct_object(key_node,deep=deep)
        if key in result:
            raise ValueError('duplicate_metadata_key')
        result[key]=loader.construct_object(value_node,deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,unique_mapping)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def linked(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def check_path(path):
    if any(linked(p) for p in (path, *path.parents)):
        raise ValueError('linked_path_rejected')


def inventory(vault, persona):
    desired = {}
    check_path(vault); check_path(persona)
    for path in sorted(vault.rglob('*')):
        check_path(path)
        if not path.is_file() or path.suffix.lower() != '.md':
            continue
        if path.stat().st_size > 2*1024*1024:
            raise ValueError('note_size_limit')
        raw = path.read_bytes()
        lines = raw.decode('utf-8-sig').splitlines()
        if not lines or lines[0].strip() != '---':
            continue
        try:
            end = next(i for i in range(1,len(lines)) if lines[i].strip() == '---')
            metadata = yaml.load('\n'.join(lines[1:end]),Loader=UniqueLoader)
        except (StopIteration, yaml.YAMLError):
            raise ValueError('invalid_note_metadata') from None
        if isinstance(metadata,dict) and metadata.get('visibility') == 'public':
            desired['vault/'+path.relative_to(vault).as_posix()] = raw
    content = load_persona(persona, target='social')
    desired['persona-social.txt'] = (render_persona(content,'social',persona)+'\n').encode('utf-8')
    return desired


def publish(vault, persona, destination, backup_root, *, apply=False):
    vault, persona, destination, backup_root = map(lambda p: Path(p).absolute(), (vault,persona,destination,backup_root))
    for path in (vault,persona,destination,backup_root):
        check_path(path)
    vault,persona,destination,backup_root=(p.resolve() for p in (vault,persona,destination,backup_root))
    for source in (vault,persona,backup_root):
        if source.is_relative_to(destination) or destination.is_relative_to(source):
            raise ValueError('overlapping_directories')
    # Never publish into the owner repository, including an unrelated subfolder.
    if destination.is_relative_to(ROOT) or ROOT.is_relative_to(destination):
        raise ValueError('owner_repository_destination_rejected')
    desired = inventory(vault,persona)
    manifest = destination/MANIFEST
    check_path(manifest)
    before = manifest.read_bytes() if manifest.exists() else None
    prior = json.loads(before) if before else {'version':1,'files':{}}
    if prior.get('version') != 1 or not isinstance(prior.get('files'),dict):
        raise ValueError('invalid_manifest')
    owned = prior['files']
    if destination.exists():
        for path in destination.rglob('*'):
            check_path(path)
            if path.is_file() and path.relative_to(destination).as_posix() not in set(owned)|{MANIFEST}:
                raise ValueError('unmanaged_public_tree')
    for name in set(owned)|set(desired):
        p = Path(name)
        if p.is_absolute() or '..' in p.parts or ':' in name or '\\' in name or name == MANIFEST:
            raise ValueError('unsafe_manifest_path')
        check_path(destination/p)
    observed = {}
    for name in set(owned)|set(desired):
        path = destination/name
        observed[name] = path.read_bytes() if path.exists() else None
        if name not in owned and observed[name] is not None:
            raise ValueError('unmanaged_destination_file')
        if name in owned and observed[name] is not None and digest(observed[name]) != owned[name]:
            raise ValueError('destination_modified_externally')
    changes = [n for n in desired if observed[n] != desired[n]]
    revoked = [n for n in owned if n not in desired and observed[n] is not None]
    result = {'public_notes':len(desired)-1,'write':len(changes),'withdraw':len(revoked),'apply':apply}
    if not apply:
        return result
    if inventory(vault,persona) != desired:
        raise ValueError('source_changed_during_publication')
    # Fail before writes if any managed file changed during planning.
    if (manifest.read_bytes() if manifest.exists() else None) != before:
        raise ValueError('publication_race')
    for name, raw in observed.items():
        path = destination/name
        if (path.read_bytes() if path.exists() else None) != raw:
            raise ValueError('publication_race')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = backup_root/stamp
    for name in changes+revoked:
        if observed[name] is not None:
            target = backup/name; target.parent.mkdir(parents=True,exist_ok=True)
            # Backups are outside the exported tree; preserve original bytes.
            target.write_bytes(observed[name])
    destination.mkdir(parents=True,exist_ok=True)
    # Withdrawal moves the old file rather than deleting it. Backup was saved.
    for name in revoked:
        target=backup/'withdrawn'/name; target.parent.mkdir(parents=True,exist_ok=True)
        (destination/name).rename(target)
    for name in changes:
        path=destination/name; path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_name(path.name+'.publish-'+stamp)
        with temporary.open('xb') as f:
            f.write(desired[name]); f.flush(); os.fsync(f.fileno())
        temporary.replace(path)
    new = json.dumps({'version':1,'files':{k:digest(v) for k,v in sorted(desired.items())}},ensure_ascii=False,indent=2).encode()
    if before != new:
        if before:
            backup.mkdir(parents=True,exist_ok=True); (backup/MANIFEST).write_bytes(before)
        temp=destination/(MANIFEST+'.'+stamp)
        temp.write_bytes(new); temp.replace(manifest)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault',type=Path,default=ROOT/'vault')
    parser.add_argument('--persona-dir',type=Path,default=DEFAULT_SOURCE_DIR)
    parser.add_argument('--out',type=Path,default=ROOT.parent/'AI-Memory-public')
    parser.add_argument('--backup-dir',type=Path,default=ROOT/'backups/public-publish')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    try:
        result=publish(args.vault,args.persona_dir,args.out,args.backup_dir,apply=args.apply)
    except (OSError,ValueError,KeyError,TypeError,yaml.YAMLError):
        print('public_publish_failed',file=sys.stderr); return 1
    print(json.dumps(result)); return 0


if __name__ == '__main__':
    raise SystemExit(main())
