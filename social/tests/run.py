"""Offline test runner. All fixtures and extracted ws files remain in --work-root.

Uses the user's existing DSH Node/ws, no npm install and no system PATH changes.
--baseline runs the identical CONTRACT assertions against unpatched pinned files.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--runtime-asar', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--work-root', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    args.work_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='social-tests-', dir=args.work_root))
    spec = importlib.util.spec_from_file_location('vendor_build', ROOT / 'build/fetch-and-patch.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    if args.baseline:
        vendor = work / 'vendor'; vendor.mkdir()
        for item in json.loads((ROOT/'vendor.lock').read_text())['projects']:
            data = subprocess.check_output(['git','-c','core.autocrlf=false','-C',str(args.source_root/item['name']),'archive',item['commit']])
            target=vendor/item['name'];target.mkdir();module.extract(data,target)
    else:
        vendor = work / 'vendor';module.materialize(vendor,args.source_root)
    # Copy existing ws source from the trusted installed runtime, never execute asar.
    ws = work/'ws';ws.mkdir()
    with args.runtime_asar.open('rb') as stream:
        header=struct.unpack('<4I',stream.read(16));tree=json.loads(stream.read(header[3]));offset=8+header[1]
        node=tree
        for part in ['dsh','node_modules','ws']:node=node['files'][part]
        def extract(node,prefix=Path()):
            for name,entry in node.get('files',{}).items():
                target=prefix/name
                if 'files' in entry:extract(entry,target)
                else:
                    if entry.get('unpacked'):raise ValueError('ws_unpacked_file_requires_explicit_source')
                    stream.seek(offset+int(entry['offset']));out=ws/target;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(stream.read(entry['size']))
        extract(node)
    env=dict(os.environ,SOCIAL_VENDOR=str(vendor),SOCIAL_WS=str(ws),SOCIAL_TEST_TMP=str(work),PYTHONDONTWRITEBYTECODE='1',TEMP=str(work),TMP=str(work))
    print('Test artifacts:',work,flush=True)
    tests=ROOT/'tests'
    command=[str(args.node),'--import',(tests/'loader.mjs').as_uri(),'--test','--test-concurrency=1']
    if args.baseline:command += [str(tests/'contracts.test.mjs')]
    else:command += [str(p) for p in sorted(tests.glob('*.test.mjs'))]
    result=subprocess.run(command,env=env)
    return result.returncode


if __name__=='__main__':raise SystemExit(main())
